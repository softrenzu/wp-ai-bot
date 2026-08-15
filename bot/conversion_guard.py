#!/usr/bin/env python3

import html
import json
import os
import re
import sys

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests


JST = timezone(timedelta(hours=9))

BOOKING_URL = (
    "https://airhost113589.airhost.co/"
    "ja/houses/565943"
)

HISTORY_FILE = Path(
    "/secrets/conversion_topics_used.json"
)

LAST_POST_FILE = Path(
    "/secrets/last_post.json"
)

MAX_NEW_POSTS_PER_WEEK = 2

# New posts are intentionally distributed across the week.
# Python weekday(): Monday=0 ... Sunday=6
NEW_POST_WEEKDAYS = {0, 4}  # Monday and Friday

SIMILARITY_LIMIT = 0.50

CURATED_TOPICS = [
    (
        "Tokyo Accommodation for Couples: "
        "Private House or Hotel?"
    ),
    (
        "Where to Stay in Tokyo as a Couple "
        "Near Shinjuku"
    ),
    (
        "Quiet Tokyo Accommodation for Two "
        "in Shibuya City"
    ),
    (
        "Traditional Japanese House Stay "
        "in Tokyo for Two"
    ),
    (
        "Tokyo Couple Stay with Tatami "
        "and Futon Bedding"
    ),
    (
        "Private House in Tokyo for Two: "
        "What to Expect"
    ),
    (
        "Hatagaya Couple Stay: "
        "A Quiet Base Near Shinjuku"
    ),
    (
        "Tokyo Accommodation for Two "
        "with More Private Space"
    ),
    (
        "Is a Traditional House Suitable "
        "for Couples in Tokyo?"
    ),
    (
        "A Local Tokyo Neighborhood Stay "
        "for Two Travelers"
    ),
    (
        "Tokyo Stay for Couples "
        "Who Prefer Privacy"
    ),
    (
        "Tokyo Private Rental Near Shinjuku "
        "for Two Travelers"
    ),
    (
        "Hotel Alternative in Tokyo "
        "for Couples"
    ),
    (
        "What Couples Should Know Before "
        "Booking a Futon Stay"
    ),
    (
        "Tokyo Accommodation for Two "
        "in a Quiet Neighborhood"
    ),
    (
        "Why Couples Choose a Private "
        "House Stay in Tokyo"
    ),
    (
        "Hatagaya or Shinjuku: "
        "Where Should a Couple Stay?"
    ),
    (
        "A Compact Private House in Tokyo "
        "for Two Guests"
    ),
    (
        "Where to Stay in Tokyo "
        "for a Quiet Couple's Trip"
    ),
    (
        "Tokyo Accommodation for Two "
        "Away from Crowded Districts"
    ),
]


def now_jst() -> datetime:
    return datetime.now(JST)


def get_wp_base_url() -> str:
    value = os.environ.get(
        "WP_URL",
        "https://staytokyo.xyz",
    ).strip()

    value = re.sub(
        r"/wp-json(?:/.*)?$",
        "",
        value,
    )

    return value.rstrip("/")


WP_BASE_URL = get_wp_base_url()

WP_USER = os.environ.get(
    "WP_USER",
    "",
)

WP_APP_PASSWORD = os.environ.get(
    "WP_APP_PASSWORD",
    "",
)


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
    value = clean_html(value).lower()

    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def tokens(value: str) -> set[str]:
    stop_words = {
        "a",
        "an",
        "and",
        "as",
        "at",
        "for",
        "from",
        "in",
        "is",
        "near",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
    }

    return {
        token
        for token in normalize(
            value
        ).split()
        if (
            len(token) >= 3
            and token not in stop_words
        )
    }


def similarity(
    first: str,
    second: str,
) -> float:

    first_tokens = tokens(first)
    second_tokens = tokens(second)

    if (
        not first_tokens
        or not second_tokens
    ):
        return 0.0

    union = (
        first_tokens
        | second_tokens
    )

    return (
        len(
            first_tokens
            & second_tokens
        )
        / len(union)
    )


def parse_datetime(
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


def load_history() -> list[dict[str, Any]]:

    if not HISTORY_FILE.exists():
        return []

    try:
        value = json.loads(
            HISTORY_FILE.read_text(
                encoding="utf-8"
            )
        )

        if isinstance(value, list):
            return value

    except Exception as error:
        print(
            "[WARN] History read failed:",
            error,
        )

    return []


def save_history(
    history: list[dict[str, Any]],
) -> None:

    HISTORY_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    HISTORY_FILE.write_text(
        json.dumps(
            history,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def fetch_published_posts() -> list[dict[str, Any]]:

    if not WP_USER or not WP_APP_PASSWORD:
        raise RuntimeError(
            "WP_USER or WP_APP_PASSWORD "
            "is not set"
        )

    endpoint = (
        WP_BASE_URL
        + "/wp-json/wp/v2/posts"
    )

    posts = []

    for page_number in range(1, 6):
        response = requests.get(
            endpoint,
            params={
                "context": "edit",
                "status": "publish",
                "orderby": "date",
                "order": "desc",
                "per_page": 100,
                "page": page_number,
                "_fields": (
                    "id,date,modified,link,"
                    "slug,title,content,"
                    "excerpt,status"
                ),
            },
            auth=(
                WP_USER,
                WP_APP_PASSWORD,
            ),
            timeout=45,
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

            content_data = (
                row.get("content") or {}
            )

            excerpt_data = (
                row.get("excerpt") or {}
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
                        "raw",
                        title_data.get(
                            "rendered",
                            "",
                        ),
                    )
                ),
                "content": (
                    content_data.get(
                        "raw",
                        content_data.get(
                            "rendered",
                            "",
                        ),
                    )
                ),
                "excerpt": clean_html(
                    excerpt_data.get(
                        "raw",
                        excerpt_data.get(
                            "rendered",
                            "",
                        ),
                    )
                ),
            })

        if len(rows) < 100:
            break

    return posts


def current_week_new_count(
    history: list[dict[str, Any]],
) -> int:

    current = now_jst()

    year, week, _ = (
        current.isocalendar()
    )

    count = 0

    for row in history:
        action = str(
            row.get(
                "action",
                "",
            )
        )

        if action not in {
            "new_post",
            "",
        }:
            continue

        used_at = parse_datetime(
            str(
                row.get(
                    "used_at",
                    "",
                )
            )
        )

        if not used_at:
            continue

        used_year, used_week, _ = (
            used_at.isocalendar()
        )

        if (
            used_year == year
            and used_week == week
        ):
            count += 1

    return count


def select_unique_topic(
    posts: list[dict[str, Any]],
    history: list[dict[str, Any]],
) -> str:

    used_topics = {
        normalize(
            str(
                row.get(
                    "topic",
                    "",
                )
            )
        )
        for row in history
        if row.get("topic")
    }

    titles = [
        post["title"]
        for post in posts
    ]

    for topic in CURATED_TOPICS:
        if normalize(topic) in used_topics:
            continue

        highest_similarity = max(
            (
                similarity(
                    topic,
                    title,
                )
                for title in titles
            ),
            default=0.0,
        )

        if (
            highest_similarity
            < SIMILARITY_LIMIT
        ):
            return topic

    return ""


def recently_refreshed_ids(
    history: list[dict[str, Any]],
    days: int = 21,
) -> set[int]:

    threshold = (
        now_jst()
        - timedelta(days=days)
    )

    result: set[int] = set()

    for row in history:
        if row.get(
            "action"
        ) != "refresh_existing":
            continue

        used_at = parse_datetime(
            str(
                row.get(
                    "used_at",
                    "",
                )
            )
        )

        if (
            not used_at
            or used_at < threshold
        ):
            continue

        try:
            result.add(
                int(
                    row.get(
                        "post_id"
                    )
                )
            )
        except Exception:
            pass

    return result


def select_refresh_post(
    posts: list[dict[str, Any]],
    history: list[dict[str, Any]],
) -> dict[str, Any]:

    relevant_terms = [
        "couple",
        "two",
        "private",
        "quiet",
        "traditional",
        "tokyo accommodation",
        "hatagaya",
        "shinjuku",
        "shibuya city",
    ]

    refreshed_ids = (
        recently_refreshed_ids(
            history
        )
    )

    candidates = []

    for post in posts:
        searchable = normalize(
            post["title"]
            + " "
            + clean_html(
                post["content"]
            )[:1200]
        )

        if not any(
            term in searchable
            for term in relevant_terms
        ):
            continue

        if int(
            post.get("id") or 0
        ) in refreshed_ids:
            continue

        modified = parse_datetime(
            post.get(
                "modified",
                "",
            )
        )

        candidates.append({
            "post": post,
            "modified": (
                modified
                or datetime(
                    2000,
                    1,
                    1,
                    tzinfo=JST,
                )
            ),
        })

    if not candidates:
        for post in posts:
            searchable = normalize(
                post["title"]
            )

            if any(
                term in searchable
                for term in relevant_terms
            ):
                modified = parse_datetime(
                    post.get(
                        "modified",
                        "",
                    )
                )

                candidates.append({
                    "post": post,
                    "modified": (
                        modified
                        or datetime(
                            2000,
                            1,
                            1,
                            tzinfo=JST,
                        )
                    ),
                })

    if not candidates:
        raise RuntimeError(
            "No suitable existing post "
            "was found for refresh"
        )

    candidates.sort(
        key=lambda item: (
            item["modified"]
        )
    )

    return candidates[0]["post"]


def word_count(value: str) -> int:
    return len(
        re.findall(
            r"[A-Za-z0-9]+"
            r"(?:'[A-Za-z0-9]+)?",
            clean_html(value),
        )
    )


def generate_refreshed_article(
    post: dict[str, Any],
) -> str:

    from main import call_chatgpt

    existing_text = clean_html(
        post["content"]
    )

    prompt = f"""
Rewrite and improve the existing WordPress article
below for direct bookings at Izumian.

Do not create a new article or a new title.
The existing WordPress URL and title will be kept.

Existing title:
{post["title"]}

Existing article:
--- START ---
{existing_text[:14000]}
--- END ---

Commercial goal:
Generate direct bookings from international couples
and two adult travelers considering Tokyo accommodation.

Verified property facts:
- Property name: 泉庵 Izumian.
- Located in Hatagaya, Shibuya City, Tokyo.
- Not beside Shibuya Station.
- Not located in Shinjuku.
- Hatagaya Station is about a 12-minute walk.
- Renovated two-story private house.
- Entire property is used by one group.
- Maximum capacity is four guests.
- Recommended comfort level is two to three guests.
- Best positioning is a private stay for a couple
  or two adult travelers.
- Tatami and futon bedding.
- Black-and-wood interior.
- Wooden spiral staircase.
- Some low-ceiling areas.
- A convenience store is about one minute away.
- Direct booking URL:
  {BOOKING_URL}

Requirements:
- Write natural English.
- WordPress-ready HTML only.
- Do not use Markdown.
- Do not include H1.
- Use H2 and H3 headings.
- 900 to 1,300 English words.
- Answer an accommodation-selection question.
- Mention Izumian within the first 200 words.
- Include accurate limitations before promotional text.
- Do not call Izumian a hotel.
- Do not describe it as luxury, spacious, barrier-free,
  childproof, beside Shibuya Station or in Shinjuku.
- Do not invent facilities, prices, travel times,
  guest quotations or nearby attractions.
- Include one direct-booking CTA at the end linking to:
  {BOOKING_URL}
- Output HTML only.
"""

    article = call_chatgpt(
        prompt,
        max_tokens=2600,
        temperature=0.35,
    ).strip()

    failed = []

    if (
        word_count(article) < 700
        or word_count(article) > 1600
    ):
        failed.append(
            "word_count"
        )

    if BOOKING_URL not in article:
        failed.append(
            "booking_link"
        )

    if "<h2" not in article.lower():
        failed.append(
            "h2"
        )

    if "<h1" in article.lower():
        failed.append(
            "h1"
        )

    if "```" in article:
        failed.append(
            "markdown_fence"
        )

    if failed:
        correction_prompt = (
            prompt
            + "\n\nThe previous output failed: "
            + ", ".join(failed)
            + ". Produce corrected HTML only."
        )

        article = call_chatgpt(
            correction_prompt,
            max_tokens=2800,
            temperature=0.25,
        ).strip()

    if word_count(article) < 700:
        raise RuntimeError(
            "Refreshed article is too short: "
            f"{word_count(article)} words"
        )

    if BOOKING_URL not in article:
        raise RuntimeError(
            "Direct booking link is missing"
        )

    if "<h1" in article.lower():
        raise RuntimeError(
            "Unexpected H1 in article"
        )

    return article


def make_excerpt(
    article: str,
) -> str:

    text = clean_html(article)

    if len(text) <= 155:
        return text

    shortened = text[:155]

    if " " in shortened:
        shortened = shortened.rsplit(
            " ",
            1,
        )[0]

    return shortened.rstrip(
        " ,.;:"
    ) + "..."


def refresh_existing(
    post: dict[str, Any],
) -> dict[str, Any]:

    article = generate_refreshed_article(
        post
    )

    response = requests.post(
        (
            f"{WP_BASE_URL}/wp-json/"
            f"wp/v2/posts/{post['id']}"
        ),
        json={
            "content": article,
            "excerpt": make_excerpt(
                article
            ),
            "status": "publish",
        },
        auth=(
            WP_USER,
            WP_APP_PASSWORD,
        ),
        timeout=90,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            "WordPress update error "
            f"{response.status_code}: "
            f"{response.text[:1200]}"
        )

    result = response.json()

    return {
        "post_id": result.get("id"),
        "url": result.get("link"),
        "title": clean_html(
            (
                result.get("title")
                or {}
            ).get(
                "rendered",
                post["title"],
            )
        ),
        "word_count": word_count(
            article
        ),
    }


def create_new_post(
    topic: str,
) -> dict[str, Any]:

    os.environ["TOPIC"] = topic

    from main import run_once

    run_once()

    result: dict[str, Any] = {
        "topic": topic,
    }

    if LAST_POST_FILE.exists():
        try:
            result.update(
                json.loads(
                    LAST_POST_FILE.read_text(
                        encoding="utf-8"
                    )
                )
            )
        except Exception:
            pass

    return result


def main() -> int:

    print(
        "[START] Direct-booking "
        "conversion guard"
    )

    posts = fetch_published_posts()
    history = load_history()

    weekly_new_count = (
        current_week_new_count(
            history
        )
    )

    unique_topic = (
        select_unique_topic(
            posts,
            history,
        )
    )

    current_weekday = now_jst().weekday()
    is_new_post_day = (
        current_weekday
        in NEW_POST_WEEKDAYS
    )

    if (
        unique_topic
        and weekly_new_count
        < MAX_NEW_POSTS_PER_WEEK
        and is_new_post_day
    ):
        print(
            "[ACTION] Creating one "
            "unique new post"
        )

        print(
            "[TOPIC]",
            unique_topic,
        )

        result = create_new_post(
            unique_topic
        )

        history.append({
            "used_at": (
                now_jst().isoformat(
                    timespec="seconds"
                )
            ),
            "action": "new_post",
            "topic": unique_topic,
            "post_id": result.get(
                "post_id",
                result.get("id"),
            ),
            "url": result.get(
                "post_link",
                result.get("url"),
            ),
        })

        save_history(history)

        print(
            "[OK] New post completed"
        )

    else:
        if (
            weekly_new_count
            >= MAX_NEW_POSTS_PER_WEEK
        ):
            reason = "weekly new-post limit"
        elif not is_new_post_day:
            reason = (
                "scheduled existing-post "
                "optimization day"
            )
        else:
            reason = "duplicate topic risk"


        print(
            "[ACTION] Refreshing an "
            "existing post"
        )

        print(
            "[REASON]",
            reason,
        )

        target = select_refresh_post(
            posts,
            history,
        )

        print(
            "[TARGET]",
            target["id"],
            target["title"],
        )

        result = refresh_existing(
            target
        )

        history.append({
            "used_at": (
                now_jst().isoformat(
                    timespec="seconds"
                )
            ),
            "action": (
                "refresh_existing"
            ),
            "reason": reason,
            "post_id": result.get(
                "post_id"
            ),
            "title": result.get(
                "title"
            ),
            "url": result.get("url"),
            "word_count": (
                result.get(
                    "word_count"
                )
            ),
        })

        save_history(history)

        print(
            "[OK] Existing post refreshed:",
            result,
        )

    print(
        "[END] Direct-booking "
        "conversion guard"
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
