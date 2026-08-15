#!/usr/bin/env python3

import argparse
import html
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests

from google.oauth2 import service_account
from googleapiclient.discovery import build


JST = timezone(timedelta(hours=9))

USER_AGENT = (
    "Mozilla/5.0 "
    "(compatible; StayTokyoIndexMonitor/1.0; "
    "+https://staytokyo.xyz/)"
)

SITE_URL = os.environ.get(
    "SEARCH_CONSOLE_SITE_URL",
    "https://staytokyo.xyz/",
).rstrip("/") + "/"

CREDENTIALS_FILE = os.environ.get(
    "GOOGLE_APPLICATION_CREDENTIALS",
    "/secrets/wordpress-gdrive.json",
)

STATUS_FILE = Path(
    "/secrets/indexing_status.json"
)

ATTENTION_FILE = Path(
    "/secrets/indexing_attention.json"
)

HISTORY_DIR = Path(
    "/secrets/indexing_history"
)

POST_989_URL = (
    "https://staytokyo.xyz/archives/989"
)


def get_wp_base_url() -> str:
    value = os.environ.get(
        "WP_URL",
        SITE_URL,
    ).strip()

    value = re.sub(
        r"/wp-json(?:/.*)?$",
        "",
        value,
    )

    return value.rstrip("/")


WP_BASE_URL = get_wp_base_url()


def now_jst() -> datetime:
    return datetime.now(JST)


def normalize_url(value: str) -> str:
    """
    URL比較用に正規化する。

    staytokyo.xyz と www.staytokyo.xyz は
    同一サイトとして比較する。
    """

    if not value:
        return ""

    parsed = urlparse(value)

    scheme = parsed.scheme.lower() or "https"

    host = (
        parsed.hostname.lower()
        if parsed.hostname
        else parsed.netloc.lower()
    )

    if host.startswith("www."):
        host = host[4:]

    port = parsed.port

    if port:
        default_port = (
            scheme == "https" and port == 443
        ) or (
            scheme == "http" and port == 80
        )

        if not default_port:
            host = f"{host}:{port}"

    path = parsed.path.rstrip("/") or "/"

    return f"{scheme}://{host}{path}"


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


def parse_wp_datetime(
    value: str,
) -> datetime | None:

    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00",
            )
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=JST
            )

        return parsed.astimezone(JST)

    except Exception:
        return None


class HeadTagParser(HTMLParser):

    def __init__(self) -> None:
        super().__init__()

        self.canonical = ""
        self.meta_robots: list[str] = []
        self.meta_googlebot: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:

        attributes = {
            str(key).lower(): (
                value or ""
            )
            for key, value in attrs
        }

        if tag.lower() == "link":
            rel = attributes.get(
                "rel",
                "",
            ).lower()

            if "canonical" in rel.split():
                self.canonical = attributes.get(
                    "href",
                    "",
                )

        if tag.lower() == "meta":
            name = attributes.get(
                "name",
                "",
            ).lower()

            content = attributes.get(
                "content",
                "",
            )

            if name == "robots":
                self.meta_robots.append(content)

            if name == "googlebot":
                self.meta_googlebot.append(content)


def http_get(
    url: str,
    timeout: int = 30,
) -> requests.Response:

    return requests.get(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "text/html,application/xml,"
                "text/xml;q=0.9,*/*;q=0.8"
            ),
        },
        timeout=timeout,
        allow_redirects=True,
    )


def fetch_robots() -> dict[str, Any]:

    robots_url = urljoin(
        SITE_URL,
        "robots.txt",
    )

    result: dict[str, Any] = {
        "url": robots_url,
        "status_code": None,
        "text": "",
        "googlebot_allowed_home": None,
        "sitemaps": [],
        "error": None,
    }

    try:
        response = http_get(
            robots_url
        )

        result["status_code"] = (
            response.status_code
        )

        result["text"] = response.text[
            :20000
        ]

        sitemaps = re.findall(
            r"(?im)^[ \t]*Sitemap:[ \t]*(\S+)",
            response.text,
        )

        result["sitemaps"] = list(
            dict.fromkeys(sitemaps)
        )

        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(
            response.text.splitlines()
        )

        result[
            "googlebot_allowed_home"
        ] = parser.can_fetch(
            "Googlebot",
            SITE_URL,
        )

    except Exception as error:
        result["error"] = (
            f"{type(error).__name__}: "
            f"{error}"
        )

    return result


def xml_local_name(tag: str) -> str:
    return tag.split("}")[-1].lower()


def parse_sitemap(
    url: str,
) -> tuple[str, list[str]]:

    response = http_get(
        url,
        timeout=45,
    )

    response.raise_for_status()

    root = ET.fromstring(
        response.content
    )

    root_type = xml_local_name(
        root.tag
    )

    locations = []

    for element in root.iter():
        if xml_local_name(
            element.tag
        ) != "loc":
            continue

        if element.text:
            locations.append(
                element.text.strip()
            )

    return root_type, locations


def discover_sitemaps(
    robots_data: dict[str, Any],
) -> dict[str, Any]:

    candidates = []

    candidates.extend(
        robots_data.get(
            "sitemaps",
            [],
        )
    )

    candidates.extend([
        urljoin(
            SITE_URL,
            "wp-sitemap.xml",
        ),
        urljoin(
            SITE_URL,
            "sitemap_index.xml",
        ),
        urljoin(
            SITE_URL,
            "sitemap.xml",
        ),
    ])

    candidates = list(
        dict.fromkeys(candidates)
    )

    root_sitemap = ""
    root_type = ""
    all_sitemaps: list[str] = []
    all_page_urls: set[str] = set()
    errors: list[dict[str, str]] = []

    for candidate in candidates:
        try:
            candidate_type, locations = (
                parse_sitemap(candidate)
            )

            if candidate_type not in {
                "sitemapindex",
                "urlset",
            }:
                continue

            root_sitemap = candidate
            root_type = candidate_type
            break

        except Exception as error:
            errors.append({
                "url": candidate,
                "error": (
                    f"{type(error).__name__}: "
                    f"{error}"
                ),
            })

    if not root_sitemap:
        return {
            "root_sitemap": "",
            "root_type": "",
            "all_sitemaps": [],
            "url_count": 0,
            "page_urls": [],
            "contains_post_989": False,
            "errors": errors,
        }

    queue = [root_sitemap]
    visited: set[str] = set()

    while queue and len(visited) < 80:
        current = queue.pop(0)

        if current in visited:
            continue

        visited.add(current)
        all_sitemaps.append(current)

        try:
            sitemap_type, locations = (
                parse_sitemap(current)
            )

            if sitemap_type == "sitemapindex":
                for location in locations:
                    if (
                        location not in visited
                        and location not in queue
                    ):
                        queue.append(location)

            elif sitemap_type == "urlset":
                for location in locations:
                    all_page_urls.add(
                        normalize_url(location)
                    )

        except Exception as error:
            errors.append({
                "url": current,
                "error": (
                    f"{type(error).__name__}: "
                    f"{error}"
                ),
            })

    normalized_989 = normalize_url(
        POST_989_URL
    )

    return {
        "root_sitemap": root_sitemap,
        "root_type": root_type,
        "all_sitemaps": all_sitemaps,
        "url_count": len(
            all_page_urls
        ),
        "page_urls": sorted(
            all_page_urls
        ),
        "contains_post_989": (
            normalized_989
            in all_page_urls
        ),
        "errors": errors,
    }


def fetch_recent_posts(
    maximum: int = 25,
) -> list[dict[str, Any]]:

    endpoint = (
        WP_BASE_URL
        + "/wp-json/wp/v2/posts"
    )

    posts = []

    for page_number in range(1, 5):
        response = requests.get(
            endpoint,
            params={
                "status": "publish",
                "orderby": "date",
                "order": "desc",
                "per_page": 100,
                "page": page_number,
                "_fields": (
                    "id,date,modified,link,"
                    "slug,title,status"
                ),
            },
            headers={
                "User-Agent": USER_AGENT,
            },
            timeout=30,
        )

        if response.status_code == 400:
            break

        response.raise_for_status()

        rows = response.json()

        if not rows:
            break

        for row in rows:
            title_data = (
                row.get("title") or {}
            )

            posts.append({
                "id": row.get("id"),
                "date": row.get(
                    "date",
                    "",
                ),
                "modified": row.get(
                    "modified",
                    "",
                ),
                "url": row.get(
                    "link",
                    "",
                ),
                "slug": row.get(
                    "slug",
                    "",
                ),
                "title": clean_html(
                    title_data.get(
                        "rendered",
                        "",
                    )
                ),
                "status": row.get(
                    "status",
                    "",
                ),
            })

        if len(rows) < 100:
            break

    posts.sort(
        key=lambda post: (
            post.get(
                "date",
                "",
            )
        ),
        reverse=True,
    )

    selected = posts[:maximum]

    if not any(
        int(post.get("id") or 0) == 989
        for post in selected
    ):
        post_989 = next(
            (
                post
                for post in posts
                if int(
                    post.get("id") or 0
                ) == 989
            ),
            None,
        )

        if post_989:
            selected.append(post_989)

    return selected


def audit_html_page(
    url: str,
    robots_text: str,
) -> dict[str, Any]:

    result: dict[str, Any] = {
        "url": url,
        "status_code": None,
        "final_url": "",
        "canonical": "",
        "canonical_matches": False,
        "meta_robots": [],
        "meta_googlebot": [],
        "x_robots_tag": "",
        "noindex": False,
        "robots_allowed": None,
        "error": None,
    }

    try:
        response = http_get(url)

        result["status_code"] = (
            response.status_code
        )

        result["final_url"] = (
            response.url
        )

        result["x_robots_tag"] = (
            response.headers.get(
                "X-Robots-Tag",
                "",
            )
        )

        parser = HeadTagParser()
        parser.feed(response.text)

        canonical = parser.canonical

        if canonical:
            canonical = urljoin(
                response.url,
                canonical,
            )

        result["canonical"] = canonical
        result["meta_robots"] = (
            parser.meta_robots
        )
        result["meta_googlebot"] = (
            parser.meta_googlebot
        )

        combined_robots = " ".join([
            result["x_robots_tag"],
            *parser.meta_robots,
            *parser.meta_googlebot,
        ]).lower()

        result["noindex"] = (
            "noindex" in combined_robots
        )

        result["canonical_matches"] = (
            bool(canonical)
            and normalize_url(canonical)
            == normalize_url(
                response.url
            )
        )

        if robots_text:
            robots_parser = RobotFileParser()
            robots_parser.parse(
                robots_text.splitlines()
            )

            result["robots_allowed"] = (
                robots_parser.can_fetch(
                    "Googlebot",
                    response.url,
                )
            )

    except Exception as error:
        result["error"] = (
            f"{type(error).__name__}: "
            f"{error}"
        )

    return result


def create_google_services():

    credentials_path = Path(
        CREDENTIALS_FILE
    )

    if not credentials_path.exists():
        raise FileNotFoundError(
            "Google credential file not found: "
            f"{CREDENTIALS_FILE}"
        )

    credentials = (
        service_account
        .Credentials
        .from_service_account_file(
            CREDENTIALS_FILE,
            scopes=[
                (
                    "https://www.googleapis.com/"
                    "auth/webmasters"
                )
            ],
        )
    )

    webmasters = build(
        "webmasters",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )

    inspection = build(
        "searchconsole",
        "v1",
        credentials=credentials,
        cache_discovery=False,
    )

    return webmasters, inspection


def submit_sitemap(
    webmasters,
    sitemap_url: str,
    force: bool,
) -> dict[str, Any]:

    result: dict[str, Any] = {
        "sitemap_url": sitemap_url,
        "listed_before": False,
        "submitted": False,
        "status": "",
        "last_submitted": None,
        "errors": None,
    }

    try:
        response = (
            webmasters
            .sitemaps()
            .list(
                siteUrl=SITE_URL
            )
            .execute()
        )

        submitted_sitemaps = (
            response.get(
                "sitemap",
                [],
            )
        )

        match = next(
            (
                item
                for item
                in submitted_sitemaps
                if normalize_url(
                    item.get(
                        "path",
                        "",
                    )
                )
                == normalize_url(
                    sitemap_url
                )
            ),
            None,
        )

        if match:
            result["listed_before"] = True
            result["last_submitted"] = (
                match.get(
                    "lastSubmitted"
                )
            )

        should_submit = (
            force
            or not match
        )

        if match and not force:
            last_submitted_text = (
                match.get(
                    "lastSubmitted",
                    "",
                )
            )

            try:
                last_submitted = (
                    datetime.fromisoformat(
                        last_submitted_text.replace(
                            "Z",
                            "+00:00",
                        )
                    )
                )

                age = (
                    datetime.now(
                        timezone.utc
                    )
                    - last_submitted.astimezone(
                        timezone.utc
                    )
                )

                if age >= timedelta(days=7):
                    should_submit = True

            except Exception:
                pass

        if should_submit:
            (
                webmasters
                .sitemaps()
                .submit(
                    siteUrl=SITE_URL,
                    feedpath=sitemap_url,
                )
                .execute()
            )

            result["submitted"] = True
            result["status"] = (
                "submitted"
            )

        else:
            result["status"] = (
                "already_submitted"
            )

    except Exception as error:
        result["status"] = "error"
        result["errors"] = (
            f"{type(error).__name__}: "
            f"{error}"
        )

    return result


def inspect_google_url(
    inspection_service,
    url: str,
) -> dict[str, Any]:

    result: dict[str, Any] = {
        "url": url,
        "verdict": "",
        "coverage_state": "",
        "robots_txt_state": "",
        "indexing_state": "",
        "page_fetch_state": "",
        "last_crawl_time": "",
        "google_canonical": "",
        "user_canonical": "",
        "referring_urls": [],
        "sitemap": [],
        "indexed": False,
        "error": None,
    }

    try:
        response = (
            inspection_service
            .urlInspection()
            .index()
            .inspect(
                body={
                    "inspectionUrl": url,
                    "siteUrl": SITE_URL,
                    "languageCode": "en-US",
                }
            )
            .execute()
        )

        index_result = (
            response
            .get(
                "inspectionResult",
                {},
            )
            .get(
                "indexStatusResult",
                {},
            )
        )

        result["verdict"] = (
            index_result.get(
                "verdict",
                "",
            )
        )

        result["coverage_state"] = (
            index_result.get(
                "coverageState",
                "",
            )
        )

        result["robots_txt_state"] = (
            index_result.get(
                "robotsTxtState",
                "",
            )
        )

        result["indexing_state"] = (
            index_result.get(
                "indexingState",
                "",
            )
        )

        result["page_fetch_state"] = (
            index_result.get(
                "pageFetchState",
                "",
            )
        )

        result["last_crawl_time"] = (
            index_result.get(
                "lastCrawlTime",
                "",
            )
        )

        result["google_canonical"] = (
            index_result.get(
                "googleCanonical",
                "",
            )
        )

        result["user_canonical"] = (
            index_result.get(
                "userCanonical",
                "",
            )
        )

        result["referring_urls"] = (
            index_result.get(
                "referringUrls",
                [],
            )
        )

        result["sitemap"] = (
            index_result.get(
                "sitemap",
                [],
            )
        )

        result["indexed"] = (
            str(
                result["verdict"]
            ).upper()
            == "PASS"
        )

    except Exception as error:
        result["error"] = (
            f"{type(error).__name__}: "
            f"{error}"
        )

    return result


def main() -> int:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--force-submit",
        action="store_true",
    )

    parser.add_argument(
        "--max-urls",
        type=int,
        default=25,
    )

    args = parser.parse_args()

    generated_at = now_jst()

    print(
        "[INFO] Site:",
        SITE_URL,
    )

    print(
        "[INFO] Fetching robots.txt..."
    )

    robots = fetch_robots()

    print(
        "[INFO] Discovering XML sitemap..."
    )

    sitemaps = discover_sitemaps(
        robots
    )

    print(
        "[INFO] Fetching recent posts..."
    )

    posts = fetch_recent_posts(
        maximum=max(
            1,
            min(
                args.max_urls,
                50,
            ),
        )
    )

    google_services_error = None
    sitemap_submission = {
        "status": "not_attempted"
    }

    inspections_by_url: dict[
        str,
        dict[str, Any]
    ] = {}

    try:
        webmasters, inspection_service = (
            create_google_services()
        )

        if sitemaps.get(
            "root_sitemap"
        ):
            print(
                "[INFO] Submitting sitemap:",
                sitemaps[
                    "root_sitemap"
                ],
            )

            sitemap_submission = (
                submit_sitemap(
                    webmasters,
                    sitemaps[
                        "root_sitemap"
                    ],
                    args.force_submit,
                )
            )

        for number, post in enumerate(
            posts,
            start=1,
        ):
            print(
                f"[INFO] Inspecting "
                f"{number}/{len(posts)}:",
                post["url"],
            )

            inspections_by_url[
                normalize_url(
                    post["url"]
                )
            ] = inspect_google_url(
                inspection_service,
                post["url"],
            )

    except Exception as error:
        google_services_error = (
            f"{type(error).__name__}: "
            f"{error}"
        )

    page_results = []
    attention = []

    sitemap_page_urls = set(
        sitemaps.get(
            "page_urls",
            [],
        )
    )

    for post in posts:
        url = post["url"]

        html_audit = audit_html_page(
            url,
            robots.get(
                "text",
                "",
            ),
        )

        google_result = (
            inspections_by_url.get(
                normalize_url(url),
                {
                    "url": url,
                    "indexed": False,
                    "error": (
                        google_services_error
                    ),
                },
            )
        )

        published_at = parse_wp_datetime(
            post.get(
                "date",
                "",
            )
        )

        age_hours = None

        if published_at:
            age_hours = round(
                (
                    generated_at
                    - published_at
                ).total_seconds()
                / 3600,
                1,
            )

        in_sitemap = (
            normalize_url(url)
            in sitemap_page_urls
        )

        attention_reasons = []

        if html_audit.get(
            "status_code"
        ) != 200:
            attention_reasons.append(
                "http_not_200"
            )

        if html_audit.get(
            "noindex",
            False,
        ):
            attention_reasons.append(
                "noindex"
            )

        if html_audit.get(
            "robots_allowed"
        ) is False:
            attention_reasons.append(
                "blocked_by_robots"
            )

        canonical = html_audit.get(
            "canonical",
            "",
        )

        if (
            canonical
            and not html_audit.get(
                "canonical_matches",
                False,
            )
        ):
            attention_reasons.append(
                "canonical_mismatch"
            )

        indexed = google_result.get(
            "indexed",
            False,
        )

        # 72時間以上経過しても未登録なら要確認
        if (
            age_hours is not None
            and age_hours >= 72
            and not indexed
        ):
            attention_reasons.append(
                "not_indexed_after_72_hours"
            )

        # サイトマップ未掲載は、24時間以上経過し、
        # かつGoogleにも未登録の場合だけ要確認
        if (
            age_hours is not None
            and age_hours >= 24
            and not in_sitemap
            and not indexed
        ):
            attention_reasons.append(
                "missing_from_sitemap"
            )

        sitemap_missing = not in_sitemap

        needs_attention = bool(
            attention_reasons
        )

        item = {
            "post_id": post.get("id"),
            "title": post.get("title"),
            "published_at": (
                post.get("date")
            ),
            "age_hours": age_hours,
            "url": url,
            "in_sitemap": in_sitemap,
            "sitemap_missing": sitemap_missing,
            "attention_reasons": attention_reasons,
            "html_audit": html_audit,
            "google": google_result,
            "needs_attention": (
                needs_attention
            ),
        }

        page_results.append(item)

        if needs_attention:
            attention.append(item)

    result = {
        "version": 1,
        "generated_at": (
            generated_at.isoformat(
                timespec="seconds"
            )
        ),
        "site_url": SITE_URL,
        "mode": (
            "sitemap_submit_and_monitor"
        ),
        "automatic_index_request": False,
        "robots": robots,
        "sitemaps": {
            key: value
            for key, value
            in sitemaps.items()
            if key != "page_urls"
        },
        "sitemap_submission": (
            sitemap_submission
        ),
        "google_services_error": (
            google_services_error
        ),
        "posts_checked": len(
            page_results
        ),
        "indexed_count": sum(
            1
            for item in page_results
            if (
                item.get(
                    "google",
                    {},
                ).get(
                    "indexed",
                    False,
                )
            )
        ),
        "attention_count": len(
            attention
        ),
        "pages": page_results,
    }

    STATUS_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    HISTORY_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    STATUS_FILE.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    ATTENTION_FILE.write_text(
        json.dumps(
            {
                "generated_at": (
                    result[
                        "generated_at"
                    ]
                ),
                "count": len(attention),
                "pages": attention,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    history_file = (
        HISTORY_DIR
        / (
            generated_at.strftime(
                "%Y%m%d-%H%M%S"
            )
            + ".json"
        )
    )

    history_file.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print(
        "===== INDEXING PIPELINE SUMMARY ====="
    )

    print(
        "robots.txt:",
        robots.get("status_code")
    )

    print(
        "Googlebot許可:",
        robots.get(
            "googlebot_allowed_home"
        )
    )

    print(
        "robots内サイトマップ:",
        robots.get("sitemaps")
    )

    print(
        "検出サイトマップ:",
        sitemaps.get(
            "root_sitemap"
        )
    )

    print(
        "サイトマップURL数:",
        sitemaps.get(
            "url_count"
        )
    )

    print(
        "記事989掲載:",
        sitemaps.get(
            "contains_post_989"
        )
    )

    print(
        "Search Console送信:",
        sitemap_submission.get(
            "status"
        )
    )

    if sitemap_submission.get(
        "errors"
    ):
        print(
            "送信エラー:",
            sitemap_submission.get(
                "errors"
            )
        )

    if google_services_error:
        print(
            "Google APIエラー:",
            google_services_error
        )

    print(
        "確認URL数:",
        len(page_results)
    )

    print(
        "登録済み:",
        result["indexed_count"]
    )

    print(
        "要確認:",
        len(attention)
    )

    post_989 = next(
        (
            item
            for item in page_results
            if int(
                item.get(
                    "post_id"
                )
                or 0
            ) == 989
        ),
        None,
    )

    if post_989:
        print()
        print("--- 記事989 ---")
        print(
            "サイトマップ:",
            post_989["in_sitemap"]
        )
        print(
            "HTTP:",
            post_989[
                "html_audit"
            ].get(
                "status_code"
            )
        )
        print(
            "noindex:",
            post_989[
                "html_audit"
            ].get(
                "noindex"
            )
        )
        print(
            "canonical:",
            post_989[
                "html_audit"
            ].get(
                "canonical"
            )
        )
        print(
            "Google判定:",
            post_989[
                "google"
            ].get(
                "verdict"
            )
        )
        print(
            "カバレッジ:",
            post_989[
                "google"
            ].get(
                "coverage_state"
            )
        )

    print()
    print(
        "状態保存:",
        STATUS_FILE
    )

    print(
        "要確認:",
        ATTENTION_FILE
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
