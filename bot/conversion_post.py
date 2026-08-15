#!/usr/bin/env python3

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests


JST = timezone(timedelta(hours=9))

WP_URL = os.environ.get(
    "WP_URL",
    "https://staytokyo.xyz",
).rstrip("/")

USED_FILE = Path(
    "/secrets/conversion_topics_used.json"
)

BOOKING_URL = (
    "https://airhost113589.airhost.co/"
    "ja/houses/565943"
)

CURATED_TOPICS = [
    "Tokyo Accommodation for Couples: Private House or Hotel?",
    "Where to Stay in Tokyo as a Couple Near Shinjuku",
    "Quiet Tokyo Accommodation for Two in Shibuya City",
    "Traditional Japanese House Stay in Tokyo for Two",
    "Tokyo Couple Stay with Tatami and Futon Bedding",
    "Private House in Tokyo for Two: What to Expect",
    "Hatagaya Couple Stay: A Quiet Base Near Shinjuku",
    "Tokyo Accommodation for Two with More Private Space",
    "Is a Traditional House Suitable for Couples in Tokyo?",
    "A Local Tokyo Neighborhood Stay for Two Travelers",
    "Tokyo Stay for Couples Who Prefer Privacy",
    "Where Can a Couple Stay Outside Busy Central Tokyo?",
    "Tokyo Private Rental for Two Near Shinjuku",
    "Hotel Alternative in Tokyo for Couples",
    "What Couples Should Know Before Booking a Futon Stay",
    "Tokyo Accommodation for Two in a Quiet Neighborhood",
    "Why Couples Choose a Private House Stay in Tokyo",
    "Hatagaya or Shinjuku: Where Should a Couple Stay?",
    "Tokyo Accommodation for Couples with a Local Atmosphere",
    "Traditional Tokyo Stay for Two with Tatami Rooms",
    "A Compact Private House in Tokyo for Two Guests",
    "Where to Stay in Tokyo for a Quiet Couple's Trip",
    "Tokyo Accommodation for Two Away from Crowded Districts",
    "Private Tokyo Stay for Couples Visiting Shinjuku",
    "What Is It Like to Stay in a Japanese House as a Couple?",
    "Tokyo Couple Accommodation with Exclusive House Use",
    "Choosing Tokyo Accommodation for Two Adults",
    "A Practical Guide to Staying in Hatagaya as a Couple",
    "Tokyo Accommodation for Couples Who Dislike Large Hotels",
    "Private House Stay Near Shinjuku for Two Travelers"
]


def now_jst() -> datetime:
    return datetime.now(JST)


def normalize(value: str) -> str:
    value = value.lower()
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


def load_used() -> list[dict[str, Any]]:
    if not USED_FILE.exists():
        return []

    try:
        data = json.loads(
            USED_FILE.read_text(
                encoding="utf-8"
            )
        )

        if isinstance(data, list):
            return data

    except Exception as error:
        print(
            "[WARN] Used-topic file error:",
            error,
        )

    return []


def fetch_existing_titles() -> list[str]:
    endpoint = (
        WP_URL
        + "/wp-json/wp/v2/posts"
    )

    titles: list[str] = []

    for page in range(1, 6):
        response = requests.get(
            endpoint,
            params={
                "per_page": 100,
                "page": page,
                "_fields": "title",
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
            title = (
                row.get("title") or {}
            ).get(
                "rendered",
                "",
            )

            title = re.sub(
                r"<[^>]+>",
                " ",
                title,
            )

            titles.append(title)

        if len(rows) < 100:
            break

    return titles


def token_similarity(
    first: str,
    second: str,
) -> float:

    first_tokens = set(
        normalize(first).split()
    )

    second_tokens = set(
        normalize(second).split()
    )

    if not first_tokens or not second_tokens:
        return 0.0

    union = first_tokens | second_tokens

    return (
        len(first_tokens & second_tokens)
        / len(union)
    )


def choose_topic(
    existing_titles: list[str],
    used_rows: list[dict[str, Any]],
) -> str:

    used_topics = {
        normalize(
            str(row.get("topic", ""))
        )
        for row in used_rows
    }

    for topic in CURATED_TOPICS:
        normalized_topic = normalize(topic)

        if normalized_topic in used_topics:
            continue

        too_similar = any(
            token_similarity(
                topic,
                existing_title,
            ) >= 0.72
            for existing_title
            in existing_titles
        )

        if too_similar:
            continue

        return topic

    return ""


def save_used(
    used_rows: list[dict[str, Any]],
    topic: str,
) -> None:

    used_rows.append({
        "used_at": now_jst().isoformat(
            timespec="seconds"
        ),
        "topic": topic,
        "booking_url": BOOKING_URL,
    })

    USED_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    USED_FILE.write_text(
        json.dumps(
            used_rows,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> int:
    used_rows = load_used()
    existing_titles = fetch_existing_titles()

    topic = choose_topic(
        existing_titles,
        used_rows,
    )

    if topic:
        os.environ["TOPIC"] = topic

        print(
            "[INFO] Conversion topic:",
            topic,
        )

    else:
        # 準備済みテーマを使い切った後も
        # cron自体は停止しない。
        # main.pyのSEO生成へ戻し、固定された
        # カップル向けフィードバックを使用する。
        os.environ.pop(
            "TOPIC",
            None,
        )

        print(
            "[INFO] Curated topics exhausted. "
            "Using the couple-focused SEO prompt."
        )

    # TOPICはmain.pyのimport時に読み込まれるため、
    # 必ず環境変数設定後にimportする。
    from main import run_once

    run_once()

    if topic:
        save_used(
            used_rows,
            topic,
        )

    print(
        "[OK] Conversion-focused post completed"
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
