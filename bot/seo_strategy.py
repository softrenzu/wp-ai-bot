#!/usr/bin/env python3

import argparse
import hashlib
import html
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build


SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly"
]

CREDENTIALS_FILE = os.environ.get(
    "GOOGLE_APPLICATION_CREDENTIALS",
    "/secrets/wordpress-gdrive.json",
)

SITE_URL = os.environ.get(
    "SEARCH_CONSOLE_SITE_URL",
    "https://staytokyo.xyz/",
)

WP_URL = os.environ.get(
    "WP_URL",
    SITE_URL,
).rstrip("/")

LOOKBACK_DAYS = int(
    os.environ.get("SEO_LOOKBACK_DAYS", "28")
)

ROW_LIMIT = int(
    os.environ.get("SEO_ROW_LIMIT", "25000")
)

STRATEGY_FILE = Path(
    os.environ.get(
        "SEO_STRATEGY_FILE",
        "/secrets/seo_strategy.json",
    )
)

SNAPSHOT_DIR = Path(
    os.environ.get(
        "SEO_SNAPSHOT_DIR",
        "/secrets/seo_snapshots",
    )
)

DOMESTIC_COUNTRY = os.environ.get(
    "SEO_DOMESTIC_COUNTRY",
    "jpn",
).lower()

JST = timezone(timedelta(hours=9))


def now_jst() -> datetime:
    return datetime.now(JST)


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_url(value: str) -> str:
    if not value:
        return ""

    parsed = urlparse(value)
    path = parsed.path.rstrip("/") or "/"

    return (
        f"{parsed.scheme.lower()}://"
        f"{parsed.netloc.lower()}{path}"
    )


def is_homepage(url: str) -> bool:
    return normalize_url(url) == normalize_url(SITE_URL)


def is_index_noise(url: str) -> bool:
    path = urlparse(url).path.lower()

    patterns = [
        "/archives/category/",
        "/category/",
        "/tag/",
        "/author/",
        "/feed",
        "/wp-json/",
    ]

    if any(pattern in path for pattern in patterns):
        return True

    if re.search(r"/page/[0-9]+/?$", path):
        return True

    return False


def make_task_id(*parts: str) -> str:
    raw = "|".join(parts)
    return hashlib.sha1(
        raw.encode("utf-8")
    ).hexdigest()[:12]


def safe_round(value: Any, digits: int = 2) -> float:
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return 0.0


def percent_change(
    current: float,
    previous: float,
) -> Optional[float]:
    if previous == 0:
        return None

    return safe_round(
        ((current - previous) / previous) * 100,
        2,
    )


def get_search_console_service():
    if not Path(CREDENTIALS_FILE).exists():
        raise FileNotFoundError(
            "Search Console credentials not found: "
            f"{CREDENTIALS_FILE}"
        )

    credentials = (
        service_account
        .Credentials
        .from_service_account_file(
            CREDENTIALS_FILE,
            scopes=SCOPES,
        )
    )

    return build(
        "searchconsole",
        "v1",
        credentials=credentials,
        cache_discovery=False,
    )


def fetch_search_console_rows(
    service,
    start_date: date,
    end_date: date,
    dimensions: List[str],
) -> List[Dict[str, Any]]:

    body = {
        "startDate": start_date.isoformat(),
        "endDate": end_date.isoformat(),
        "dimensions": dimensions,
        "type": "web",
        "dataState": "final",
        "rowLimit": ROW_LIMIT,
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

    result: List[Dict[str, Any]] = []

    for row in response.get("rows", []):
        keys = row.get("keys", [])

        item: Dict[str, Any] = {}

        for index, dimension in enumerate(dimensions):
            item[dimension] = (
                keys[index]
                if index < len(keys)
                else ""
            )

        item.update({
            "clicks": float(
                row.get("clicks", 0)
            ),
            "impressions": float(
                row.get("impressions", 0)
            ),
            "ctr": float(
                row.get("ctr", 0)
            ),
            "position": float(
                row.get("position", 0)
            ),
        })

        result.append(item)

    return result


def fetch_wordpress_posts(
    maximum_pages: int = 10,
) -> List[Dict[str, Any]]:

    endpoint = (
        WP_URL
        + "/wp-json/wp/v2/posts"
    )

    posts: List[Dict[str, Any]] = []

    for page_number in range(
        1,
        maximum_pages + 1,
    ):
        response = requests.get(
            endpoint,
            params={
                "per_page": 100,
                "page": page_number,
                "_fields": (
                    "id,date,modified,link,slug,"
                    "title,excerpt"
                ),
            },
            timeout=30,
        )

        if response.status_code == 400:
            break

        response.raise_for_status()

        page_posts = response.json()

        if not page_posts:
            break

        for post in page_posts:
            title_data = (
                post.get("title") or {}
            )
            excerpt_data = (
                post.get("excerpt") or {}
            )

            posts.append({
                "id": post.get("id"),
                "date": post.get("date", ""),
                "modified": post.get(
                    "modified",
                    "",
                ),
                "link": post.get("link", ""),
                "normalized_url": normalize_url(
                    post.get("link", "")
                ),
                "slug": post.get("slug", ""),
                "title": clean_text(
                    title_data.get(
                        "rendered",
                        "",
                    )
                ),
                "excerpt": clean_text(
                    excerpt_data.get(
                        "rendered",
                        "",
                    )
                ),
            })

        if len(page_posts) < 100:
            break

    return posts


def aggregate_rows(
    rows: Iterable[Dict[str, Any]],
    key_fields: List[str],
    predicate: Optional[
        Callable[[Dict[str, Any]], bool]
    ] = None,
) -> Dict[
    Tuple[str, ...],
    Dict[str, Any],
]:

    aggregated: Dict[
        Tuple[str, ...],
        Dict[str, Any],
    ] = {}

    for row in rows:
        if predicate and not predicate(row):
            continue

        key = tuple(
            str(row.get(field, ""))
            for field in key_fields
        )

        if key not in aggregated:
            aggregated[key] = {
                field: row.get(field, "")
                for field in key_fields
            }
            aggregated[key].update({
                "clicks": 0.0,
                "impressions": 0.0,
                "_position_total": 0.0,
            })

        item = aggregated[key]

        impressions = float(
            row.get("impressions", 0)
        )
        clicks = float(
            row.get("clicks", 0)
        )
        position = float(
            row.get("position", 0)
        )

        item["clicks"] += clicks
        item["impressions"] += impressions
        item["_position_total"] += (
            position * impressions
        )

    for item in aggregated.values():
        impressions = item["impressions"]
        clicks = item["clicks"]

        item["ctr"] = (
            clicks / impressions
            if impressions
            else 0.0
        )

        item["position"] = (
            item["_position_total"]
            / impressions
            if impressions
            else 0.0
        )

        item.pop(
            "_position_total",
            None,
        )

    return aggregated


def summarize_segment(
    page_country_rows: List[
        Dict[str, Any]
    ],
    predicate: Callable[
        [Dict[str, Any]],
        bool,
    ],
) -> Dict[str, Any]:

    pages = aggregate_rows(
        page_country_rows,
        ["page"],
        predicate,
    )

    clicks = sum(
        item["clicks"]
        for item in pages.values()
    )
    impressions = sum(
        item["impressions"]
        for item in pages.values()
    )

    weighted_position = sum(
        item["position"]
        * item["impressions"]
        for item in pages.values()
    )

    return {
        "clicks": safe_round(
            clicks,
            0,
        ),
        "impressions": safe_round(
            impressions,
            0,
        ),
        "ctr_percent": safe_round(
            (
                clicks / impressions * 100
                if impressions
                else 0
            ),
            2,
        ),
        "position": safe_round(
            (
                weighted_position
                / impressions
                if impressions
                else 0
            ),
            2,
        ),
        "pages_with_impressions": len(
            pages
        ),
    }


def expected_ctr(
    position: float,
) -> float:

    if position <= 3:
        return 0.08

    if position <= 5:
        return 0.05

    if position <= 10:
        return 0.03

    if position <= 20:
        return 0.015

    return 0.01


def is_relevant_query(
    query: str,
) -> bool:
    """
    泉庵の宿泊予約や周辺滞在に関係する
    検索語だけを採用する。

    単に「Tokyo」や他社ホテル名が含まれる
    だけの検索語は改善材料にしない。
    """

    query = (
        query
        .strip()
        .lower()
    )

    if not query:
        return False

    property_terms = [
        "izumian",
        "泉庵",
        "hatagaya",
        "幡ヶ谷",
    ]

    location_terms = [
        "tokyo",
        "東京",
        "shibuya",
        "渋谷",
        "shinjuku",
        "新宿",
        "hatagaya",
        "幡ヶ谷",
    ]

    accommodation_terms = [
        "accommodation",
        "private house",
        "private rental",
        "traditional house",
        "traditional stay",
        "vacation rental",
        "holiday rental",
        "guesthouse",
        "guest house",
        "airbnb",
        "ryokan",
        "family stay",
        "quiet stay",
        "long stay",
        "tatami",
        "futon",
    ]

    competitor_or_noise_terms = [
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
        "tokyo 1 hotel",
        "東京阿泉",
        "青水庵",
    ]

    has_property_term = any(
        term in query
        for term in property_terms
    )

    if any(
        term in query
        for term in competitor_or_noise_terms
    ) and not has_property_term:
        return False

    if has_property_term:
        return True

    has_location = any(
        term in query
        for term in location_terms
    )

    has_accommodation_intent = any(
        term in query
        for term in accommodation_terms
    )

    return (
        has_location
        and has_accommodation_intent
    )


def public_metrics(
    item: Optional[Dict[str, Any]],
) -> Dict[str, Any]:

    item = item or {}

    return {
        "clicks": safe_round(
            item.get("clicks", 0),
            0,
        ),
        "impressions": safe_round(
            item.get("impressions", 0),
            0,
        ),
        "ctr_percent": safe_round(
            item.get("ctr", 0) * 100,
            2,
        ),
        "position": safe_round(
            item.get("position", 0),
            2,
        ),
    }


def build_tasks(
    current_page_country: List[
        Dict[str, Any]
    ],
    previous_page_country: List[
        Dict[str, Any]
    ],
    current_detail: List[
        Dict[str, Any]
    ],
    previous_detail: List[
        Dict[str, Any]
    ],
    posts: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:

    is_international = lambda row: (
        str(
            row.get("country", "")
        ).lower()
        != DOMESTIC_COUNTRY
    )

    current_pages = aggregate_rows(
        current_page_country,
        ["page"],
        is_international,
    )

    previous_pages = aggregate_rows(
        previous_page_country,
        ["page"],
        is_international,
    )

    current_query_pages = aggregate_rows(
        current_detail,
        ["query", "page"],
        is_international,
    )

    previous_query_pages = aggregate_rows(
        previous_detail,
        ["query", "page"],
        is_international,
    )

    current_queries = aggregate_rows(
        current_detail,
        ["query"],
        is_international,
    )

    posts_by_url = {
        post["normalized_url"]: post
        for post in posts
    }

    query_items_by_page: Dict[
        str,
        List[Dict[str, Any]],
    ] = defaultdict(list)

    for item in current_query_pages.values():
        query_items_by_page[
            normalize_url(
                item.get("page", "")
            )
        ].append(item)

    raw_tasks: List[Dict[str, Any]] = []

    # 既存ページの改善候補
    for key, metrics in current_pages.items():
        page_url = key[0]
        normalized = normalize_url(page_url)

        if is_index_noise(page_url):
            continue

        impressions = metrics["impressions"]
        clicks = metrics["clicks"]
        ctr = metrics["ctr"]
        position = metrics["position"]

        # 極端に少ないデータは
        # 自動判断に使用しない
        if impressions < 5:
            continue

        if position <= 0 or position > 40:
            continue

        previous = previous_pages.get(
            (page_url,)
        )

        query_items = sorted(
            [
                item
                for item
                in query_items_by_page.get(
                    normalized,
                    [],
                )
                if is_relevant_query(
                    str(
                        item.get(
                            "query",
                            "",
                        )
                    )
                )
            ],
            key=lambda item: (
                item["impressions"],
                item["clicks"],
            ),
            reverse=True,
        )[:5]

        relevant_impressions = sum(
            item["impressions"]
            for item in query_items
        )

        # 無関係な検索語しかないページは
        # SEO改善対象にしない
        if relevant_impressions < 3:
            continue

        title = (
            posts_by_url
            .get(normalized, {})
            .get("title", "")
        )

        post_id = (
            posts_by_url
            .get(normalized, {})
            .get("id")
        )

        target_ctr = expected_ctr(
            position
        )

        if is_homepage(page_url):
            action = (
                "improve_landing_page"
            )
            reason = (
                "The homepage receives "
                "international impressions. "
                "Its search intent and booking "
                "message should be aligned with "
                "the actual queries."
            )
            score_multiplier = 1.4

        elif (
            position <= 12
            and ctr < target_ctr
        ):
            action = (
                "rewrite_title_meta"
            )
            reason = (
                "The page has usable rankings "
                "but CTR is below the minimum "
                "target for its position."
            )
            score_multiplier = 1.3

        else:
            action = (
                "refresh_existing"
            )
            reason = (
                "The page already receives "
                "international impressions and "
                "should be improved before "
                "creating another similar page."
            )
            score_multiplier = 1.0

        score = (
            impressions
            * max(
                1.0,
                41.0 - min(position, 40),
            )
            * score_multiplier
            * (
                1.15
                if clicks == 0
                else 1.0
            )
        )

        raw_tasks.append({
            "task_id": make_task_id(
                action,
                page_url,
            ),
            "score": safe_round(
                score,
                2,
            ),
            "action": action,
            "status": "pending_review",
            "auto_execute_allowed": False,
            "target_url": page_url,
            "post_id": post_id,
            "current_title": title,
            "target_queries": [
                {
                    "query": item.get(
                        "query",
                        "",
                    ),
                    **public_metrics(item),
                }
                for item in query_items
            ],
            "reason": reason,
            "baseline": public_metrics(
                metrics
            ),
            "previous_period": (
                public_metrics(previous)
                if previous
                else None
            ),
            "required_work": [
                (
                    "Confirm the dominant "
                    "search intent."
                ),
                (
                    "Rewrite the title and "
                    "opening around actual "
                    "queries, not a generic "
                    "travel theme."
                ),
                (
                    "Add factual Izumian details "
                    "that support a booking "
                    "decision."
                ),
                (
                    "Avoid creating a second "
                    "page targeting the same "
                    "queries."
                ),
            ],
        })

    # 同一クエリで複数ページが表示される
    # カニバリゼーション候補
    pages_by_query: Dict[
        str,
        List[Dict[str, Any]],
    ] = defaultdict(list)

    for item in current_query_pages.values():
        query = str(
            item.get("query", "")
        ).strip()
        page = str(
            item.get("page", "")
        )

        if not query:
            continue

        if is_index_noise(page):
            continue

        if item["impressions"] < 2:
            continue

        pages_by_query[query].append(
            item
        )

    for query, page_items in pages_by_query.items():
        unique_pages = {
            normalize_url(
                item.get("page", "")
            )
            for item in page_items
        }

        total_impressions = sum(
            item["impressions"]
            for item in page_items
        )

        if (
            len(unique_pages) < 2
            or total_impressions < 5
        ):
            continue

        page_items.sort(
            key=lambda item: (
                item["impressions"],
                item["clicks"],
            ),
            reverse=True,
        )

        raw_tasks.append({
            "task_id": make_task_id(
                "consolidate_or_differentiate",
                query,
            ),
            "score": safe_round(
                total_impressions * 35,
                2,
            ),
            "action": (
                "consolidate_or_differentiate"
            ),
            "status": "pending_review",
            "auto_execute_allowed": False,
            "target_query": query,
            "reason": (
                "Multiple pages are receiving "
                "impressions for the same query. "
                "Creating more similar articles "
                "may divide ranking signals."
            ),
            "pages": [
                {
                    "url": item.get(
                        "page",
                        "",
                    ),
                    **public_metrics(item),
                }
                for item in page_items
            ],
            "required_work": [
                (
                    "Choose one primary page "
                    "for this query."
                ),
                (
                    "Differentiate, merge, "
                    "redirect, or internally "
                    "link competing pages."
                ),
                (
                    "Do not publish another "
                    "article for this query."
                ),
            ],
        })

    # 実際に表示されているクエリから
    # 新規コンテンツ調査候補を抽出
    for key, metrics in current_queries.items():
        query = key[0].strip()

        if not query:
            continue

        if not is_relevant_query(
            query
        ):
            continue

        impressions = metrics["impressions"]
        position = metrics["position"]

        if impressions < 3:
            continue

        if position <= 12:
            continue

        matching_pages = [
            item
            for item
            in current_query_pages.values()
            if item.get("query") == query
        ]

        real_article_pages = [
            item
            for item in matching_pages
            if (
                not is_homepage(
                    item.get("page", "")
                )
                and not is_index_noise(
                    item.get("page", "")
                )
            )
        ]

        if real_article_pages:
            continue

        raw_tasks.append({
            "task_id": make_task_id(
                "research_content_gap",
                query,
            ),
            "score": safe_round(
                impressions
                * max(
                    1.0,
                    min(position, 40),
                ),
                2,
            ),
            "action": (
                "research_content_gap"
            ),
            "status": "pending_review",
            "auto_execute_allowed": False,
            "target_query": query,
            "reason": (
                "The query has accommodation "
                "or destination intent, but no "
                "specific article page is "
                "clearly serving it."
            ),
            "baseline": public_metrics(
                metrics
            ),
            "required_work": [
                (
                    "Verify that the query "
                    "matches Izumian and has "
                    "booking relevance."
                ),
                (
                    "Check whether an existing "
                    "page can be expanded first."
                ),
                (
                    "Create a new page only when "
                    "no suitable page exists."
                ),
            ],
        })

    # 重複タスクを除外
    deduplicated: Dict[
        str,
        Dict[str, Any],
    ] = {}

    for task in raw_tasks:
        task_id = task["task_id"]

        if (
            task_id not in deduplicated
            or task["score"]
            > deduplicated[
                task_id
            ]["score"]
        ):
            deduplicated[task_id] = task

    tasks = sorted(
        deduplicated.values(),
        key=lambda task: task["score"],
        reverse=True,
    )[:25]

    for index, task in enumerate(
        tasks,
        start=1,
    ):
        task["priority"] = index
        task.pop("score", None)

    return tasks


def country_summary(
    rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:

    aggregated = aggregate_rows(
        rows,
        ["country"],
    )

    result = []

    for key, metrics in aggregated.items():
        result.append({
            "country": key[0],
            **public_metrics(metrics),
        })

    result.sort(
        key=lambda item: (
            item["impressions"],
            item["clicks"],
        ),
        reverse=True,
    )

    return result[:20]


def query_summary(
    rows: List[Dict[str, Any]],
    international_only: bool,
) -> List[Dict[str, Any]]:

    if international_only:
        predicate = lambda row: (
            str(
                row.get("country", "")
            ).lower()
            != DOMESTIC_COUNTRY
        )
    else:
        predicate = lambda row: True

    aggregated = aggregate_rows(
        rows,
        ["query"],
        predicate,
    )

    result = []

    for key, metrics in aggregated.items():
        query = key[0].strip()

        if not query:
            continue

        result.append({
            "query": query,
            **public_metrics(metrics),
        })

    result.sort(
        key=lambda item: (
            item["impressions"],
            item["clicks"],
        ),
        reverse=True,
    )

    return result[:50]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build an analysis-only SEO "
            "strategy queue."
        )
    )

    parser.add_argument(
        "--output",
        default=str(STRATEGY_FILE),
    )

    args = parser.parse_args()

    generated_at = now_jst()

    # Search Consoleは直近数日が
    # 未確定になるため3日前を終点にする
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

    previous_end = (
        current_start
        - timedelta(days=1)
    )
    previous_start = (
        previous_end
        - timedelta(
            days=LOOKBACK_DAYS - 1
        )
    )

    print(
        "[INFO] Search Console property:",
        SITE_URL,
    )
    print(
        "[INFO] Current period:",
        current_start,
        "to",
        current_end,
    )
    print(
        "[INFO] Previous period:",
        previous_start,
        "to",
        previous_end,
    )

    service = (
        get_search_console_service()
    )

    print(
        "[INFO] Fetching current "
        "page-country data..."
    )
    current_page_country = (
        fetch_search_console_rows(
            service,
            current_start,
            current_end,
            ["page", "country"],
        )
    )

    print(
        "[INFO] Fetching previous "
        "page-country data..."
    )
    previous_page_country = (
        fetch_search_console_rows(
            service,
            previous_start,
            previous_end,
            ["page", "country"],
        )
    )

    print(
        "[INFO] Fetching current "
        "query-page-country data..."
    )
    current_detail = (
        fetch_search_console_rows(
            service,
            current_start,
            current_end,
            [
                "query",
                "page",
                "country",
            ],
        )
    )

    print(
        "[INFO] Fetching previous "
        "query-page-country data..."
    )
    previous_detail = (
        fetch_search_console_rows(
            service,
            previous_start,
            previous_end,
            [
                "query",
                "page",
                "country",
            ],
        )
    )

    print(
        "[INFO] Fetching WordPress posts..."
    )
    posts = fetch_wordpress_posts()

    domestic_current = summarize_segment(
        current_page_country,
        lambda row: (
            str(
                row.get("country", "")
            ).lower()
            == DOMESTIC_COUNTRY
        ),
    )

    domestic_previous = summarize_segment(
        previous_page_country,
        lambda row: (
            str(
                row.get("country", "")
            ).lower()
            == DOMESTIC_COUNTRY
        ),
    )

    international_current = (
        summarize_segment(
            current_page_country,
            lambda row: (
                str(
                    row.get(
                        "country",
                        "",
                    )
                ).lower()
                != DOMESTIC_COUNTRY
            ),
        )
    )

    international_previous = (
        summarize_segment(
            previous_page_country,
            lambda row: (
                str(
                    row.get(
                        "country",
                        "",
                    )
                ).lower()
                != DOMESTIC_COUNTRY
            ),
        )
    )

    international_impressions = (
        international_current[
            "impressions"
        ]
    )

    if international_impressions < 50:
        data_level = "very_low"
    elif international_impressions < 200:
        data_level = "low"
    else:
        data_level = "usable"

    tasks = build_tasks(
        current_page_country,
        previous_page_country,
        current_detail,
        previous_detail,
        posts,
    )

    strategy = {
        "version": 1,
        "generated_at": (
            generated_at.isoformat(
                timespec="seconds"
            )
        ),
        "mode": "analysis_only",
        "auto_publish": False,
        "manual_review_required": True,
        "site_url": SITE_URL,
        "domestic_country": (
            DOMESTIC_COUNTRY
        ),
        "periods": {
            "current": {
                "start": (
                    current_start
                    .isoformat()
                ),
                "end": (
                    current_end
                    .isoformat()
                ),
                "days": LOOKBACK_DAYS,
            },
            "previous": {
                "start": (
                    previous_start
                    .isoformat()
                ),
                "end": (
                    previous_end
                    .isoformat()
                ),
                "days": LOOKBACK_DAYS,
            },
        },
        "metrics": {
            "international": {
                "current": (
                    international_current
                ),
                "previous": (
                    international_previous
                ),
                "changes": {
                    "clicks_percent": (
                        percent_change(
                            international_current[
                                "clicks"
                            ],
                            international_previous[
                                "clicks"
                            ],
                        )
                    ),
                    "impressions_percent": (
                        percent_change(
                            international_current[
                                "impressions"
                            ],
                            international_previous[
                                "impressions"
                            ],
                        )
                    ),
                },
            },
            "japan": {
                "current": domestic_current,
                "previous": domestic_previous,
                "changes": {
                    "clicks_percent": (
                        percent_change(
                            domestic_current[
                                "clicks"
                            ],
                            domestic_previous[
                                "clicks"
                            ],
                        )
                    ),
                    "impressions_percent": (
                        percent_change(
                            domestic_current[
                                "impressions"
                            ],
                            domestic_previous[
                                "impressions"
                            ],
                        )
                    ),
                },
            },
        },
        "diagnostics": {
            "international_data_level": (
                data_level
            ),
            "wordpress_posts_found": len(
                posts
            ),
            "current_page_country_rows": len(
                current_page_country
            ),
            "current_query_rows": len(
                current_detail
            ),
            "task_count": len(tasks),
            "daily_new_posts_recommended": False,
            "reason": (
                "Do not modify pages when "
                "Search Console data is sparse "
                "or the observed queries are "
                "not relevant to Izumian. "
                "External search-demand research "
                "is required before selecting "
                "new target keywords."
            ),
        },
        "top_countries": country_summary(
            current_page_country
        ),
        "top_international_queries": (
            query_summary(
                current_detail,
                international_only=True,
            )
        ),
        "tasks": tasks,
    }

    output_file = Path(
        args.output
    )
    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_file.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            strategy,
            file,
            ensure_ascii=False,
            indent=2,
        )

    SNAPSHOT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    snapshot_file = (
        SNAPSHOT_DIR
        / (
            generated_at.strftime(
                "%Y%m%d-%H%M%S"
            )
            + ".json"
        )
    )

    snapshot = {
        "generated_at": (
            generated_at.isoformat(
                timespec="seconds"
            )
        ),
        "periods": strategy["periods"],
        "current_page_country": (
            current_page_country
        ),
        "previous_page_country": (
            previous_page_country
        ),
        "current_detail": (
            current_detail
        ),
        "previous_detail": (
            previous_detail
        ),
    }

    with snapshot_file.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            snapshot,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print(
        "[OK] Strategy written:",
        output_file,
    )
    print(
        "[OK] Snapshot written:",
        snapshot_file,
    )
    print(
        "[RESULT] International:",
        international_current,
    )
    print(
        "[RESULT] Japan:",
        domestic_current,
    )
    print(
        "[RESULT] Tasks:",
        len(tasks),
    )

    for task in tasks[:10]:
        print(
            f"  {task['priority']}. "
            f"{task['action']} "
            f"{task.get('target_url', '')} "
            f"{task.get('target_query', '')}"
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
