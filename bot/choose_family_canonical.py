#!/usr/bin/env python3

import html
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build


JST = timezone(timedelta(hours=9))

SITE_URL = os.environ.get(
    "SEARCH_CONSOLE_SITE_URL",
    "https://staytokyo.xyz/",
)

WP_URL = os.environ.get(
    "WP_URL",
    "https://staytokyo.xyz",
).rstrip("/")

CREDENTIALS_FILE = os.environ.get(
    "GOOGLE_APPLICATION_CREDENTIALS",
    "/secrets/wordpress-gdrive.json",
)

OUTPUT_FILE = Path(
    os.environ.get(
        "FAMILY_CANONICAL_PLAN_FILE",
        "/secrets/family_canonical_plan.json",
    )
)

LOOKBACK_DAYS = int(
    os.environ.get(
        "CANONICAL_LOOKBACK_DAYS",
        "90",
    )
)

# STEP5で上位になった記事。
# 投稿IDを直接指定して、不要な270記事全体を
# 再度候補にしない。
CANDIDATE_IDS = [
    922,
    974,
    882,
    931,
    928,
    937,
    986,
    946,
    971,
    980,
    977,
    952,
    943,
    934,
    949,
]

PRIMARY_KEYWORD = (
    "tokyo accommodation for family of 4"
)

SECONDARY_KEYWORDS = [
    "tokyo accommodation for 4",
    "where to stay in tokyo with family",
    "where to stay in tokyo family of 4",
    "family accommodation tokyo",
    "family stay in tokyo",
    "private house in tokyo for family",
    "family accommodation near shinjuku",
]

BOOKING_URL = (
    "https://airhost113589.airhost.co/"
    "ja/houses/565943"
)


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
    return clean_html(
        value
    ).lower().strip()


def normalize_url(value: str) -> str:
    parsed = urlparse(value)

    path = (
        parsed.path.rstrip("/")
        or "/"
    )

    return (
        f"{parsed.scheme.lower()}://"
        f"{parsed.netloc.lower()}"
        f"{path}"
    )


def word_count(value: str) -> int:
    return len(
        re.findall(
            r"[A-Za-z0-9]+",
            clean_html(value),
        )
    )


def get_search_console_service():
    credentials_path = Path(
        CREDENTIALS_FILE
    )

    if not credentials_path.exists():
        raise FileNotFoundError(
            "Search Console credentials "
            f"not found: {CREDENTIALS_FILE}"
        )

    credentials = (
        service_account
        .Credentials
        .from_service_account_file(
            CREDENTIALS_FILE,
            scopes=[
                (
                    "https://www.googleapis.com/"
                    "auth/webmasters.readonly"
                )
            ],
        )
    )

    return build(
        "searchconsole",
        "v1",
        credentials=credentials,
        cache_discovery=False,
    )


def fetch_candidate_posts() -> list[dict[str, Any]]:
    endpoint = (
        WP_URL
        + "/wp-json/wp/v2/posts"
    )

    results = []

    for post_id in CANDIDATE_IDS:
        response = requests.get(
            f"{endpoint}/{post_id}",
            params={
                "_fields": (
                    "id,date,modified,link,slug,"
                    "title,content,excerpt,status"
                )
            },
            timeout=30,
        )

        if response.status_code == 404:
            print(
                "[WARN] Post not found:",
                post_id,
            )
            continue

        response.raise_for_status()

        item = response.json()

        title_data = (
            item.get("title")
            or {}
        )

        content_data = (
            item.get("content")
            or {}
        )

        excerpt_data = (
            item.get("excerpt")
            or {}
        )

        results.append({
            "id": item.get("id"),
            "date": item.get("date", ""),
            "modified": item.get(
                "modified",
                "",
            ),
            "url": item.get("link", ""),
            "normalized_url": normalize_url(
                item.get("link", "")
            ),
            "slug": item.get("slug", ""),
            "status": item.get(
                "status",
                "",
            ),
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
            "content_text": clean_html(
                content_data.get(
                    "rendered",
                    "",
                )
            ),
            "excerpt": clean_html(
                excerpt_data.get(
                    "rendered",
                    "",
                )
            ),
        })

    return results


def fetch_gsc_rows(
    service,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:

    body = {
        "startDate": start_date.isoformat(),
        "endDate": end_date.isoformat(),
        "dimensions": [
            "query",
            "page",
            "country",
        ],
        "type": "web",
        "dataState": "final",
        "rowLimit": 25000,
        "startRow": 0,
    }

    response = (
        service
        .searchanalytics()
        .query(
            siteUrl=SITE_URL,
            body=body,
        )
        .execute()
    )

    result = []

    for row in response.get(
        "rows",
        [],
    ):
        keys = row.get(
            "keys",
            [],
        )

        result.append({
            "query": (
                keys[0]
                if len(keys) > 0
                else ""
            ),
            "page": (
                keys[1]
                if len(keys) > 1
                else ""
            ),
            "country": (
                keys[2]
                if len(keys) > 2
                else ""
            ),
            "clicks": float(
                row.get(
                    "clicks",
                    0,
                )
            ),
            "impressions": float(
                row.get(
                    "impressions",
                    0,
                )
            ),
            "ctr": float(
                row.get(
                    "ctr",
                    0,
                )
            ),
            "position": float(
                row.get(
                    "position",
                    0,
                )
            ),
        })

    return result


def summarize_gsc(
    rows: list[dict[str, Any]],
    url: str,
) -> dict[str, Any]:

    normalized = normalize_url(url)

    matching = [
        row
        for row in rows
        if normalize_url(
            row.get(
                "page",
                "",
            )
        ) == normalized
    ]

    clicks = sum(
        row["clicks"]
        for row in matching
    )

    impressions = sum(
        row["impressions"]
        for row in matching
    )

    position_total = sum(
        row["position"]
        * row["impressions"]
        for row in matching
    )

    overseas_rows = [
        row
        for row in matching
        if str(
            row.get(
                "country",
                "",
            )
        ).lower() != "jpn"
    ]

    overseas_clicks = sum(
        row["clicks"]
        for row in overseas_rows
    )

    overseas_impressions = sum(
        row["impressions"]
        for row in overseas_rows
    )

    query_map: dict[
        str,
        dict[str, float],
    ] = {}

    for row in matching:
        query = str(
            row.get(
                "query",
                "",
            )
        ).strip()

        if not query:
            continue

        if query not in query_map:
            query_map[query] = {
                "clicks": 0.0,
                "impressions": 0.0,
                "position_total": 0.0,
            }

        query_map[query]["clicks"] += (
            row["clicks"]
        )

        query_map[query]["impressions"] += (
            row["impressions"]
        )

        query_map[query][
            "position_total"
        ] += (
            row["position"]
            * row["impressions"]
        )

    top_queries = []

    for query, metrics in query_map.items():
        query_impressions = metrics[
            "impressions"
        ]

        top_queries.append({
            "query": query,
            "clicks": round(
                metrics["clicks"],
                0,
            ),
            "impressions": round(
                query_impressions,
                0,
            ),
            "position": round(
                (
                    metrics[
                        "position_total"
                    ]
                    / query_impressions
                    if query_impressions
                    else 0
                ),
                2,
            ),
        })

    top_queries.sort(
        key=lambda item: (
            item["impressions"],
            item["clicks"],
        ),
        reverse=True,
    )

    return {
        "clicks": round(
            clicks,
            0,
        ),
        "impressions": round(
            impressions,
            0,
        ),
        "ctr_percent": round(
            (
                clicks
                / impressions
                * 100
                if impressions
                else 0
            ),
            2,
        ),
        "position": round(
            (
                position_total
                / impressions
                if impressions
                else 0
            ),
            2,
        ),
        "overseas_clicks": round(
            overseas_clicks,
            0,
        ),
        "overseas_impressions": round(
            overseas_impressions,
            0,
        ),
        "top_queries": top_queries[:10],
    }


def evaluate_content(
    post: dict[str, Any],
) -> dict[str, Any]:

    title = normalize(
        post.get(
            "title",
            "",
        )
    )

    body = normalize(
        post.get(
            "content_text",
            "",
        )
    )

    score = 0
    reasons = []

    family_present = any(
        term in body
        for term in [
            "family",
            "families",
            "children",
            "kids",
        ]
    )

    capacity_four_present = any(
        term in body
        for term in [
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

    recommended_two_three = any(
        term in body
        for term in [
            "recommended for 2 to 3",
            "recommended for two to three",
            "best for 2 to 3",
            "best for two to three",
            "ideal for 2 to 3",
            "ideal for two to three",
        ]
    )

    private_house_present = any(
        term in body
        for term in [
            "private house",
            "private rental",
            "whole house",
            "one group per day",
        ]
    )

    property_details = {
        "tatami": (
            "tatami" in body
        ),
        "futon": (
            "futon" in body
        ),
        "spiral_staircase": (
            "spiral staircase" in body
        ),
        "low_ceiling": (
            "low ceiling" in body
        ),
        "black_and_wood": (
            (
                "black-and-wood"
                in body
            )
            or (
                "black and wood"
                in body
            )
        ),
    }

    booking_link_present = (
        BOOKING_URL
        in post.get(
            "content_html",
            "",
        )
    )

    keyword_matches = []

    for keyword in (
        [PRIMARY_KEYWORD]
        + SECONDARY_KEYWORDS
    ):
        keyword_n = normalize(keyword)

        in_title = keyword_n in title
        in_body = keyword_n in body

        if in_title:
            score += 35

        if in_body:
            score += 15

        if in_title or in_body:
            keyword_matches.append({
                "keyword": keyword,
                "in_title": in_title,
                "in_body": in_body,
            })

    if family_present:
        score += 15
        reasons.append(
            "Family-related content exists."
        )

    if capacity_four_present:
        score += 20
        reasons.append(
            "Maximum-four capacity is stated."
        )

    if recommended_two_three:
        score += 8
        reasons.append(
            "Recommended comfort level is stated."
        )

    if private_house_present:
        score += 12
        reasons.append(
            "Private-house positioning exists."
        )

    property_detail_count = sum(
        1
        for value in property_details.values()
        if value
    )

    score += (
        property_detail_count
        * 4
    )

    if booking_link_present:
        score += 5

    if word_count(
        post.get(
            "content_text",
            "",
        )
    ) >= 700:
        score += 5

    return {
        "content_score": score,
        "family_present": (
            family_present
        ),
        "capacity_four_present": (
            capacity_four_present
        ),
        "recommended_two_to_three_present": (
            recommended_two_three
        ),
        "private_house_present": (
            private_house_present
        ),
        "property_details": property_details,
        "booking_link_present": (
            booking_link_present
        ),
        "keyword_matches": (
            keyword_matches
        ),
        "reasons": reasons,
    }


def calculate_total_score(
    content: dict[str, Any],
    gsc: dict[str, Any],
    post: dict[str, Any],
) -> tuple[float, list[str]]:

    score = float(
        content.get(
            "content_score",
            0,
        )
    )

    reasons = list(
        content.get(
            "reasons",
            [],
        )
    )

    impressions = float(
        gsc.get(
            "impressions",
            0,
        )
    )

    clicks = float(
        gsc.get(
            "clicks",
            0,
        )
    )

    overseas_impressions = float(
        gsc.get(
            "overseas_impressions",
            0,
        )
    )

    position = float(
        gsc.get(
            "position",
            0,
        )
    )

    # 既に検索評価があるURLを優先する。
    score += min(
        impressions,
        100,
    ) * 0.7

    score += min(
        clicks,
        10,
    ) * 12

    score += min(
        overseas_impressions,
        30,
    ) * 1.5

    if (
        impressions >= 5
        and 0 < position <= 20
    ):
        score += 20
        reasons.append(
            "The URL already has usable "
            "Search Console visibility."
        )

    if clicks > 0:
        reasons.append(
            "The URL has already received "
            "organic clicks."
        )

    if overseas_impressions > 0:
        reasons.append(
            "The URL has overseas impressions."
        )

    # 古いURLはインデックス履歴が長い可能性があるため、
    # 内容が同程度なら僅かに優先する。
    date_text = post.get(
        "date",
        "",
    )

    try:
        published = datetime.fromisoformat(
            date_text
        )

        age_days = (
            datetime.now(
                published.tzinfo
                or timezone.utc
            )
            - published
        ).days

        score += min(
            max(
                age_days,
                0,
            ),
            365,
        ) * 0.02
    except Exception:
        pass

    return round(
        score,
        2,
    ), reasons


def main() -> int:
    print(
        "[INFO] Fetching candidate posts..."
    )

    posts = fetch_candidate_posts()

    current_end = (
        date.today()
        - timedelta(days=3)
    )

    current_start = (
        current_end
        - timedelta(
            days=LOOKBACK_DAYS - 1
        )
    )

    print(
        "[INFO] GSC period:",
        current_start,
        "to",
        current_end,
    )

    service = (
        get_search_console_service()
    )

    print(
        "[INFO] Fetching Search Console data..."
    )

    rows = fetch_gsc_rows(
        service,
        current_start,
        current_end,
    )

    evaluated = []

    for post in posts:
        content = evaluate_content(
            post
        )

        gsc = summarize_gsc(
            rows,
            post.get(
                "url",
                "",
            ),
        )

        total_score, reasons = (
            calculate_total_score(
                content,
                gsc,
                post,
            )
        )

        evaluated.append({
            "post_id": post.get("id"),
            "title": post.get("title"),
            "url": post.get("url"),
            "date": post.get("date"),
            "modified": post.get(
                "modified"
            ),
            "word_count": word_count(
                post.get(
                    "content_text",
                    "",
                )
            ),
            "total_score": total_score,
            "content": content,
            "search_console": gsc,
            "selection_reasons": reasons,
        })

    evaluated.sort(
        key=lambda item: (
            item["total_score"],
            item[
                "search_console"
            ]["impressions"],
            item[
                "search_console"
            ]["clicks"],
        ),
        reverse=True,
    )

    canonical = (
        evaluated[0]
        if evaluated
        else None
    )

    duplicates = [
        {
            "post_id": item["post_id"],
            "title": item["title"],
            "url": item["url"],
            "search_console": (
                item["search_console"]
            ),
            "proposed_action": (
                "review_for_merge_or_redirect"
            ),
        }
        for item in evaluated[1:]
    ]

    output = {
        "version": 1,
        "generated_at": now_jst().isoformat(
            timespec="seconds"
        ),
        "mode": "analysis_only",
        "wordpress_modified": False,
        "site_url": SITE_URL,
        "gsc_period": {
            "start": (
                current_start.isoformat()
            ),
            "end": (
                current_end.isoformat()
            ),
            "days": LOOKBACK_DAYS,
        },
        "target_cluster": {
            "primary_keyword": (
                PRIMARY_KEYWORD
            ),
            "secondary_keywords": (
                SECONDARY_KEYWORDS
            ),
        },
        "candidate_count": len(
            evaluated
        ),
        "recommended_canonical": (
            canonical
        ),
        "other_candidates": (
            evaluated[1:]
        ),
        "duplicate_review_queue": (
            duplicates
        ),
        "next_action": (
            "Create a replacement draft for "
            "the recommended canonical URL. "
            "Do not publish and do not redirect "
            "duplicate URLs until the draft has "
            "been reviewed."
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
        "[OK] Plan written:",
        OUTPUT_FILE,
    )

    if canonical:
        print(
            "[RESULT] Recommended canonical:",
            canonical["post_id"],
            canonical["url"],
        )
    else:
        print(
            "[RESULT] No canonical selected"
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
