#!/usr/bin/env python3

import html
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests


JST = timezone(timedelta(hours=9))

WP_URL = os.environ.get(
    "WP_URL",
    "https://staytokyo.xyz",
).rstrip("/")

OUTPUT_FILE = Path(
    os.environ.get(
        "KEYWORD_BOOTSTRAP_FILE",
        "/secrets/keyword_bootstrap.json",
    )
)

MARKETS = [
    {
        "name": "United States",
        "gl": "us",
        "hl": "en",
    },
    {
        "name": "United Kingdom",
        "gl": "gb",
        "hl": "en",
    },
    {
        "name": "Australia",
        "gl": "au",
        "hl": "en",
    },
    {
        "name": "Canada",
        "gl": "ca",
        "hl": "en",
    },
    {
        "name": "Singapore",
        "gl": "sg",
        "hl": "en",
    },
]

SEEDS = [
    "where to stay in tokyo",
    "tokyo accommodation",
    "tokyo private house",
    "traditional house stay tokyo",
    "family accommodation tokyo",
    "family stay near shinjuku",
    "tokyo vacation rental",
    "tokyo whole house rental",
    "shinjuku family accommodation",
    "shibuya private house",
    "hatagaya accommodation",
    "private house near shinjuku",
    "tokyo accommodation for 4",
    "tokyo long stay accommodation",
    "tatami stay tokyo",
    "futon stay tokyo",
    "quiet area to stay in tokyo",
    "hotel alternative tokyo",
    "authentic japanese house stay tokyo",
]

LOCATION_TERMS = [
    "tokyo",
    "shinjuku",
    "shibuya",
    "hatagaya",
]

LODGING_TERMS = [
    "stay",
    "accommodation",
    "hotel",
    "house",
    "rental",
    "airbnb",
    "ryokan",
    "guesthouse",
    "guest house",
    "lodging",
    "where to stay",
]

PROPERTY_FIT_TERMS = [
    "private",
    "whole house",
    "traditional",
    "japanese house",
    "family",
    "quiet",
    "tatami",
    "futon",
    "long stay",
    "for 4",
    "four people",
    "group",
    "near shinjuku",
    "local area",
]

HIGH_INTENT_TERMS = [
    "where to stay",
    "best",
    "book",
    "accommodation",
    "private house",
    "whole house",
    "vacation rental",
    "for family",
    "for 4",
    "near shinjuku",
]

EXCLUDED_TERMS = [
    "park hyatt",
    "hyatt",
    "hilton",
    "marriott",
    "sheraton",
    "ritz carlton",
    "ritz-carlton",
    "mandarin oriental",
    "four seasons",
    "apa hotel",
    "toyoko inn",
    "job",
    "jobs",
    "career",
    "salary",
    "for sale",
    "real estate",
    "restaurant",
    "menu",
    "phone number",
    "address",
    "map",
]

STOP_WORDS = {
    "a",
    "an",
    "and",
    "at",
    "best",
    "for",
    "from",
    "in",
    "is",
    "near",
    "of",
    "on",
    "the",
    "to",
    "with",
}


def now_jst() -> datetime:
    return datetime.now(JST)


def normalize_text(value: str) -> str:
    value = unicodedata.normalize(
        "NFKC",
        value or "",
    )
    value = html.unescape(value)
    value = value.replace("’", "'")
    value = re.sub(
        r"\s+",
        " ",
        value,
    )
    return value.strip().lower()


def clean_html(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(
        r"<[^>]+>",
        " ",
        value,
    )
    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def query_tokens(value: str) -> set[str]:
    normalized = normalize_text(value)
    words = re.findall(
        r"[a-z0-9]+",
        normalized,
    )

    return {
        word
        for word in words
        if (
            len(word) >= 2
            and word not in STOP_WORDS
        )
    }


def is_relevant_query(query: str) -> bool:
    query = normalize_text(query)

    if not query:
        return False

    if any(
        term in query
        for term in EXCLUDED_TERMS
    ):
        return False

    has_location = any(
        term in query
        for term in LOCATION_TERMS
    )

    has_lodging_intent = any(
        term in query
        for term in LODGING_TERMS
    )

    return (
        has_location
        and has_lodging_intent
    )


def classify_cluster(query: str) -> str:
    query = normalize_text(query)

    if any(
        term in query
        for term in [
            "family",
            "kids",
            "children",
            "for 4",
            "four people",
            "group",
        ]
    ):
        return "family_and_small_groups"

    if any(
        term in query
        for term in [
            "traditional",
            "japanese house",
            "tatami",
            "futon",
            "ryokan",
            "authentic",
        ]
    ):
        return "traditional_japanese_stay"

    if any(
        term in query
        for term in [
            "long stay",
            "extended stay",
            "monthly",
        ]
    ):
        return "long_stay"

    if "hatagaya" in query:
        return "hatagaya_location"

    if any(
        term in query
        for term in [
            "private house",
            "whole house",
            "vacation rental",
            "private rental",
            "airbnb",
        ]
    ):
        return "private_house_rental"

    if any(
        term in query
        for term in [
            "where to stay",
            "quiet area",
            "best area",
        ]
    ):
        return "area_selection"

    if "shinjuku" in query:
        return "near_shinjuku"

    if "shibuya" in query:
        return "shibuya_city"

    return "general_tokyo_accommodation"


def fetch_suggestions(
    seed: str,
    market: dict[str, str],
) -> list[str]:

    response = requests.get(
        "https://suggestqueries.google.com/complete/search",
        params={
            "client": "firefox",
            "q": seed,
            "hl": market["hl"],
            "gl": market["gl"],
        },
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(compatible; IzumianSEOResearch/1.0)"
            ),
            "Accept": "application/json",
        },
        timeout=15,
    )

    response.raise_for_status()

    data = response.json()

    if (
        not isinstance(data, list)
        or len(data) < 2
        or not isinstance(data[1], list)
    ):
        return []

    return [
        normalize_text(str(item))
        for item in data[1]
        if str(item).strip()
    ]


def fetch_wordpress_titles() -> list[dict[str, Any]]:
    endpoint = (
        WP_URL
        + "/wp-json/wp/v2/posts"
    )

    results: list[dict[str, Any]] = []

    for page_number in range(1, 11):
        response = requests.get(
            endpoint,
            params={
                "per_page": 100,
                "page": page_number,
                "_fields": (
                    "id,link,title,date"
                ),
            },
            timeout=20,
        )

        if response.status_code == 400:
            break

        response.raise_for_status()

        items = response.json()

        if not items:
            break

        for item in items:
            title_data = (
                item.get("title")
                or {}
            )

            title = clean_html(
                title_data.get(
                    "rendered",
                    "",
                )
            )

            results.append({
                "id": item.get("id"),
                "url": item.get("link", ""),
                "title": title,
                "tokens": query_tokens(title),
            })

        if len(items) < 100:
            break

    return results


def find_existing_coverage(
    query: str,
    posts: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    q_tokens = query_tokens(query)

    if len(q_tokens) < 2:
        return []

    matches: list[dict[str, Any]] = []

    for post in posts:
        title_tokens = post.get(
            "tokens",
            set(),
        )

        if not title_tokens:
            continue

        overlap = len(
            q_tokens & title_tokens
        ) / len(q_tokens)

        normalized_title = normalize_text(
            post.get("title", "")
        )

        normalized_query = normalize_text(
            query
        )

        if (
            overlap >= 0.60
            or normalized_query
            in normalized_title
        ):
            matches.append({
                "post_id": post.get("id"),
                "title": post.get("title", ""),
                "url": post.get("url", ""),
                "token_overlap": round(
                    overlap,
                    2,
                ),
            })

    matches.sort(
        key=lambda item: item[
            "token_overlap"
        ],
        reverse=True,
    )

    return matches[:3]


def main() -> int:
    generated_at = now_jst()

    print(
        "[INFO] Fetching existing "
        "WordPress titles..."
    )

    try:
        posts = fetch_wordpress_titles()
    except Exception as error:
        print(
            "[WARN] WordPress title fetch failed:",
            str(error),
        )
        posts = []

    candidates: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []

    def ensure_candidate(
        query: str,
    ) -> dict[str, Any]:

        normalized = normalize_text(query)

        if normalized not in candidates:
            candidates[normalized] = {
                "query": normalized,
                "suggestion_markets": set(),
                "seed_markets": set(),
                "matched_seeds": set(),
                "sources": set(),
            }

        return candidates[normalized]

    for seed in SEEDS:
        if is_relevant_query(seed):
            candidate = ensure_candidate(seed)
            candidate["sources"].add(
                "manual_seed"
            )
            candidate["matched_seeds"].add(
                seed
            )

    total_requests = (
        len(SEEDS)
        * len(MARKETS)
    )

    request_number = 0

    for market in MARKETS:
        for seed in SEEDS:
            request_number += 1

            print(
                f"[INFO] Suggest "
                f"{request_number}/{total_requests}: "
                f"{market['name']} | {seed}"
            )

            try:
                suggestions = fetch_suggestions(
                    seed,
                    market,
                )

                for suggestion in suggestions:
                    if not is_relevant_query(
                        suggestion
                    ):
                        continue

                    candidate = ensure_candidate(
                        suggestion
                    )

                    candidate[
                        "suggestion_markets"
                    ].add(
                        market["name"]
                    )

                    candidate[
                        "matched_seeds"
                    ].add(seed)

                    candidate["sources"].add(
                        "google_suggest"
                    )

                seed_candidate = (
                    ensure_candidate(seed)
                )

                seed_candidate[
                    "seed_markets"
                ].add(
                    market["name"]
                )

            except Exception as error:
                errors.append({
                    "market": market["name"],
                    "seed": seed,
                    "error": str(error),
                })

                print(
                    "[WARN] Suggest fetch failed:",
                    market["name"],
                    seed,
                    str(error),
                )

            time.sleep(0.15)

    result_candidates: list[
        dict[str, Any]
    ] = []

    for candidate in candidates.values():
        query = candidate["query"]

        if not is_relevant_query(query):
            continue

        suggestion_markets = sorted(
            candidate[
                "suggestion_markets"
            ]
        )

        matched_seeds = sorted(
            candidate["matched_seeds"]
        )

        sources = sorted(
            candidate["sources"]
        )

        fit_terms = [
            term
            for term in PROPERTY_FIT_TERMS
            if term in query
        ]

        high_intent_terms = [
            term
            for term in HIGH_INTENT_TERMS
            if term in query
        ]

        score = (
            len(suggestion_markets) * 30
            + len(matched_seeds) * 4
            + len(fit_terms) * 7
            + len(high_intent_terms) * 6
        )

        if (
            "google_suggest"
            not in sources
        ):
            score -= 20

        coverage = find_existing_coverage(
            query,
            posts,
        )

        result_candidates.append({
            "query": query,
            "score": score,
            "cluster": classify_cluster(
                query
            ),
            "suggestion_market_count": len(
                suggestion_markets
            ),
            "suggestion_markets": (
                suggestion_markets
            ),
            "matched_seed_count": len(
                matched_seeds
            ),
            "matched_seeds": (
                matched_seeds
            ),
            "property_fit_terms": fit_terms,
            "high_intent_terms": (
                high_intent_terms
            ),
            "sources": sources,
            "existing_coverage": coverage,
            "coverage_status": (
                "possibly_covered"
                if coverage
                else "not_clearly_covered"
            ),
        })

    result_candidates.sort(
        key=lambda item: (
            item["score"],
            item[
                "suggestion_market_count"
            ],
            item["matched_seed_count"],
            item["query"],
        ),
        reverse=True,
    )

    cluster_counts: dict[str, int] = {}

    for item in result_candidates:
        cluster = item["cluster"]
        cluster_counts[cluster] = (
            cluster_counts.get(
                cluster,
                0,
            )
            + 1
        )

    output = {
        "version": 1,
        "generated_at": generated_at.isoformat(
            timespec="seconds"
        ),
        "site_url": WP_URL,
        "mode": "research_only",
        "auto_publish": False,
        "auto_update_wordpress": False,
        "data_description": (
            "Google search suggestion appearance "
            "across selected English-speaking "
            "markets. This is not monthly "
            "search-volume data."
        ),
        "markets": MARKETS,
        "seed_count": len(SEEDS),
        "request_count": total_requests,
        "wordpress_posts_checked": len(
            posts
        ),
        "candidate_count": len(
            result_candidates
        ),
        "google_suggest_supported_count": sum(
            1
            for item in result_candidates
            if (
                "google_suggest"
                in item["sources"]
            )
        ),
        "cluster_counts": cluster_counts,
        "errors": errors,
        "candidates": result_candidates[:80],
        "recommended_next_action": (
            "Select one booking-relevant keyword "
            "cluster, confirm existing-page "
            "coverage, and improve one pillar "
            "page before creating additional "
            "articles."
        ),
    }

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_FILE.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "[OK] Keyword research written:",
        OUTPUT_FILE,
    )

    print(
        "[RESULT] Candidates:",
        len(result_candidates),
    )

    print(
        "[RESULT] Suggest-supported:",
        output[
            "google_suggest_supported_count"
        ],
    )

    print(
        "[RESULT] Errors:",
        len(errors),
    )

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(
            "[FATAL]",
            type(error).__name__,
            str(error),
            file=sys.stderr,
        )
        raise
