#!/usr/bin/env python3

import html
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests


JST = timezone(timedelta(hours=9))

WP_URL = os.environ.get(
    "WP_URL",
    "https://staytokyo.xyz",
).rstrip("/")

OUTPUT_FILE = Path(
    os.environ.get(
        "FAMILY_CLUSTER_AUDIT_FILE",
        "/secrets/family_cluster_audit.json",
    )
)

BOOKING_URL = (
    "https://airhost113589.airhost.co/"
    "ja/houses/565943"
)

TARGET_CLUSTER = {
    "primary_keyword": (
        "tokyo accommodation for family of 4"
    ),
    "secondary_keywords": [
        "tokyo accommodation for 4",
        "where to stay in tokyo with family",
        "where to stay in tokyo family of 4",
        "family accommodation tokyo",
        "family stay tokyo",
        "private house tokyo family",
        "family accommodation near shinjuku",
    ],
}

SIGNALS = {
    "family of 4": 20,
    "family of four": 20,
    "for a family of 4": 20,
    "for a family of four": 20,
    "accommodation for 4": 16,
    "accommodation for four": 16,
    "4 guests": 15,
    "four guests": 15,
    "maximum 4 guests": 18,
    "maximum of 4 guests": 18,
    "family accommodation": 12,
    "family stay": 10,
    "traveling with children": 8,
    "travelling with children": 8,
    "traveling with kids": 8,
    "travelling with kids": 8,
    "private house": 8,
    "private rental": 8,
    "whole house": 8,
    "near shinjuku": 6,
    "shinjuku": 4,
    "tokyo": 2,
}

EXCLUSION_SIGNALS = [
    "family of 5",
    "family of five",
    "5 guests",
    "five guests",
    "large group",
    "large groups",
]

STOP_WORDS = {
    "a", "an", "and", "are", "as", "at",
    "be", "by", "for", "from", "in", "is",
    "it", "near", "of", "on", "or", "stay",
    "the", "to", "tokyo", "with", "your",
}


def now_jst() -> datetime:
    return datetime.now(JST)


def clean_html(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        value,
        flags=re.IGNORECASE | re.DOTALL,
    )
    value = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        value,
        flags=re.IGNORECASE | re.DOTALL,
    )
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


def normalize(value: str) -> str:
    value = unicodedata.normalize(
        "NFKC",
        clean_html(value),
    )
    value = value.replace("’", "'")
    value = value.lower()
    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def word_count(value: str) -> int:
    return len(
        re.findall(
            r"[A-Za-z0-9]+",
            clean_html(value),
        )
    )


def tokens(value: str) -> set[str]:
    words = re.findall(
        r"[a-z0-9]+",
        normalize(value),
    )

    return {
        word
        for word in words
        if (
            len(word) >= 3
            and word not in STOP_WORDS
        )
    }


def fetch_items(
    content_type: str,
) -> list[dict[str, Any]]:

    endpoint = (
        WP_URL
        + f"/wp-json/wp/v2/{content_type}"
    )

    results: list[dict[str, Any]] = []

    for page_number in range(1, 21):
        response = requests.get(
            endpoint,
            params={
                "per_page": 100,
                "page": page_number,
                "_fields": (
                    "id,date,modified,link,slug,"
                    "title,content,excerpt"
                ),
            },
            timeout=30,
        )

        if response.status_code == 400:
            break

        response.raise_for_status()

        items = response.json()

        if not items:
            break

        for item in items:
            title_data = item.get("title") or {}
            content_data = item.get("content") or {}
            excerpt_data = item.get("excerpt") or {}

            results.append({
                "content_type": content_type,
                "id": item.get("id"),
                "date": item.get("date", ""),
                "modified": item.get(
                    "modified",
                    "",
                ),
                "url": item.get("link", ""),
                "slug": item.get("slug", ""),
                "title": clean_html(
                    title_data.get(
                        "rendered",
                        "",
                    )
                ),
                "content_html": content_data.get(
                    "rendered",
                    "",
                ),
                "excerpt": clean_html(
                    excerpt_data.get(
                        "rendered",
                        "",
                    )
                ),
            })

        if len(items) < 100:
            break

    return results


def evaluate_item(
    item: dict[str, Any],
) -> dict[str, Any]:

    title = item.get("title", "")
    body = item.get("content_html", "")
    excerpt = item.get("excerpt", "")

    title_n = normalize(title)
    body_n = normalize(body)
    excerpt_n = normalize(excerpt)

    score = 0
    matched_signals = []

    primary = TARGET_CLUSTER[
        "primary_keyword"
    ]

    secondary = TARGET_CLUSTER[
        "secondary_keywords"
    ]

    exact_primary_title = (
        primary in title_n
    )
    exact_primary_body = (
        primary in body_n
    )

    if exact_primary_title:
        score += 60

    if exact_primary_body:
        score += 30

    matched_keywords = []

    for keyword in [primary] + secondary:
        in_title = keyword in title_n
        in_body = keyword in body_n
        in_excerpt = keyword in excerpt_n

        if in_title:
            score += 24

        if in_body:
            score += 10

        if in_excerpt:
            score += 6

        if in_title or in_body or in_excerpt:
            matched_keywords.append({
                "keyword": keyword,
                "title": in_title,
                "body": in_body,
                "excerpt": in_excerpt,
            })

    for signal, weight in SIGNALS.items():
        in_title = signal in title_n
        in_body = signal in body_n

        if in_title:
            score += weight * 2

        if in_body:
            score += weight

        if in_title or in_body:
            matched_signals.append({
                "signal": signal,
                "title": in_title,
                "body": in_body,
            })

    exclusion_hits = [
        signal
        for signal in EXCLUSION_SIGNALS
        if (
            signal in title_n
            or signal in body_n
        )
    ]

    score -= len(exclusion_hits) * 20

    family_present = any(
        phrase in body_n
        for phrase in [
            "family",
            "families",
            "children",
            "kids",
        ]
    )

    capacity_four_present = any(
        phrase in body_n
        for phrase in [
            "4 guests",
            "four guests",
            "maximum 4",
            "maximum of 4",
            "up to 4",
            "up to four",
            "family of 4",
            "family of four",
        ]
    )

    recommendation_two_three_present = any(
        phrase in body_n
        for phrase in [
            "recommended for 2 to 3",
            "recommended for two to three",
            "best for 2 to 3",
            "best for two to three",
            "ideal for 2 to 3",
            "ideal for two to three",
        ]
    )

    property_specific_present = all(
        signal in body_n
        for signal in [
            "tatami",
            "futon",
            "spiral staircase",
        ]
    )

    booking_url_present = (
        BOOKING_URL in body
    )

    if family_present:
        score += 8

    if capacity_four_present:
        score += 15

    if recommendation_two_three_present:
        score += 8

    if property_specific_present:
        score += 10

    if booking_url_present:
        score += 5

    return {
        "content_type": item.get(
            "content_type"
        ),
        "id": item.get("id"),
        "date": item.get("date"),
        "modified": item.get("modified"),
        "url": item.get("url"),
        "slug": item.get("slug"),
        "title": title,
        "score": score,
        "word_count": word_count(body),
        "exact_primary_title": (
            exact_primary_title
        ),
        "exact_primary_body": (
            exact_primary_body
        ),
        "matched_keywords": (
            matched_keywords
        ),
        "matched_signals": (
            matched_signals
        ),
        "exclusion_hits": exclusion_hits,
        "checks": {
            "family_present": (
                family_present
            ),
            "capacity_four_present": (
                capacity_four_present
            ),
            "recommended_two_to_three_present": (
                recommendation_two_three_present
            ),
            "property_specific_details_present": (
                property_specific_present
            ),
            "booking_url_present": (
                booking_url_present
            ),
        },
        "_tokens": tokens(
            title + " " + body
        ),
    }


def find_duplicate_pairs(
    evaluated: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    candidates = [
        item
        for item in evaluated
        if item["score"] >= 15
    ][:20]

    pairs = []

    for index, first in enumerate(candidates):
        first_tokens = first.get(
            "_tokens",
            set(),
        )

        if not first_tokens:
            continue

        for second in candidates[index + 1:]:
            second_tokens = second.get(
                "_tokens",
                set(),
            )

            if not second_tokens:
                continue

            union = first_tokens | second_tokens

            if not union:
                continue

            similarity = (
                len(first_tokens & second_tokens)
                / len(union)
            )

            if similarity >= 0.45:
                pairs.append({
                    "similarity": round(
                        similarity,
                        3,
                    ),
                    "first": {
                        "id": first.get("id"),
                        "title": first.get(
                            "title"
                        ),
                        "url": first.get("url"),
                    },
                    "second": {
                        "id": second.get("id"),
                        "title": second.get(
                            "title"
                        ),
                        "url": second.get("url"),
                    },
                })

    pairs.sort(
        key=lambda pair: pair["similarity"],
        reverse=True,
    )

    return pairs[:20]


def main() -> int:
    print(
        "[INFO] Fetching WordPress posts..."
    )
    posts = fetch_items("posts")

    print(
        "[INFO] Fetching WordPress pages..."
    )
    pages = fetch_items("pages")

    all_items = posts + pages

    evaluated = [
        evaluate_item(item)
        for item in all_items
    ]

    evaluated.sort(
        key=lambda item: (
            item["score"],
            item["word_count"],
        ),
        reverse=True,
    )

    relevant = [
        item
        for item in evaluated
        if item["score"] > 0
    ]

    top = relevant[0] if relevant else None

    strong_existing_coverage = bool(
        top
        and (
            top["exact_primary_title"]
            or top["exact_primary_body"]
            or (
                top["score"] >= 70
                and top["checks"][
                    "family_present"
                ]
                and top["checks"][
                    "capacity_four_present"
                ]
            )
        )
    )

    if strong_existing_coverage:
        recommendation = "update_existing"
        reason = (
            "An existing page already covers "
            "the family-of-four search intent. "
            "Improve that page instead of "
            "creating another competing page."
        )
    else:
        recommendation = "create_new_pillar_page"
        reason = (
            "No existing page clearly covers "
            "Tokyo accommodation for a family "
            "of four. Create one pillar page "
            "and use related keyword variants "
            "within the same page."
        )

    for item in evaluated:
        item.pop("_tokens", None)

    output = {
        "version": 1,
        "generated_at": now_jst().isoformat(
            timespec="seconds"
        ),
        "site_url": WP_URL,
        "mode": "audit_only",
        "wordpress_modified": False,
        "target_cluster": TARGET_CLUSTER,
        "posts_checked": len(posts),
        "pages_checked": len(pages),
        "recommendation": recommendation,
        "recommendation_reason": reason,
        "best_existing_candidate": top,
        "top_existing_candidates": (
            relevant[:20]
        ),
        "possible_duplicate_pairs": (
            find_duplicate_pairs(
                [
                    evaluate_item(item)
                    for item in all_items
                ]
            )
        ),
        "content_requirements_for_next_step": [
            (
                "Use one page for all family-of-four "
                "keyword variants."
            ),
            (
                "State accurately that maximum "
                "capacity is four guests."
            ),
            (
                "State that two to three guests "
                "is the recommended comfort level."
            ),
            (
                "Do not target families of five "
                "or larger groups."
            ),
            (
                "Explain the private-house, tatami, "
                "futon and spiral-staircase experience."
            ),
            (
                "Explain access to Shinjuku without "
                "claiming the property is in Shinjuku."
            ),
            (
                "Include the official booking link."
            ),
        ],
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
        "[OK] Audit written:",
        OUTPUT_FILE,
    )
    print(
        "[RESULT] Posts checked:",
        len(posts),
    )
    print(
        "[RESULT] Pages checked:",
        len(pages),
    )
    print(
        "[RESULT] Recommendation:",
        recommendation,
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
