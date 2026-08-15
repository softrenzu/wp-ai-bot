#!/usr/bin/env python3

import html
import json
import os
import re
import sys
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

WP_USER = os.environ.get(
    "WP_USER",
    "",
)

WP_APP_PASSWORD = os.environ.get(
    "WP_APP_PASSWORD",
    "",
)

SOURCE_POST_ID = 946

TITLE = (
    "Tokyo Accommodation for Couples in a Private House"
)

SLUG = (
    "tokyo-accommodation-for-couples-private-house"
)

META_DESCRIPTION = (
    "Stay at Izumian, a private traditional-style house "
    "in Hatagaya, Tokyo, for a quiet couple’s trip with "
    "easy access to Shinjuku and local streets."
)

PRIMARY_KEYWORD = (
    "tokyo accommodation for couples"
)

BOOKING_URL = (
    "https://airhost113589.airhost.co/"
    "ja/houses/565943"
)

RESULT_FILE = Path(
    "/secrets/couples_draft_result.json"
)

LOCAL_HTML_FILE = Path(
    "/app/drafts/"
    "tokyo-accommodation-for-couples.html"
)

CONTENT = r"""
<p>Choosing Tokyo accommodation for couples is not only about finding a room near a famous station. For two people, privacy, a manageable layout, a calm place to return to, and convenient access to central Tokyo can matter more than a large hotel lobby. Izumian is a renovated two-story private house in Hatagaya, Shibuya City. One group uses the entire house, so a couple can stay without sharing kitchens, corridors, or living areas with other guests.</p>

<p>Izumian can host up to four guests, but the recommended comfort level is two to three people. That makes a stay for two the most natural use of the house. A couple has space to use the tatami areas, prepare for the day without crowding each other, and experience a compact Japanese home rather than a standard hotel room. The property is not beside Shibuya Station and is not located in Shinjuku. It is in a quiet residential part of Hatagaya, around a 12-minute walk from Hatagaya Station.</p>

<h2>Why Izumian Works Well for Two Guests</h2>

<p>For a couple, the strongest feature is exclusive use of the entire property. A hotel room normally combines sleeping, luggage storage, and relaxation in one limited area. Izumian provides a private-house setting across two floors. The space is still compact, but two guests can use it more comfortably than a larger group.</p>

<p>The interior combines black-and-wood styling with traditional elements such as tatami and futon bedding. The experience is different from sleeping in a Western-style bed. Futons are placed on the tatami and can be folded away, helping the room serve more than one purpose. Couples who want a practical taste of Japanese residential life may find this more memorable than a conventional hotel layout.</p>

<p>Privacy also changes the pace of a trip. There is no need to coordinate around other guests inside the property. One person can get ready while the other rests, luggage can remain inside the house, and the couple can plan the next day in a private setting. Izumian is not a luxury villa and should not be presented as spacious, but for two guests the compact scale is generally easier to manage.</p>

<h2>A Quiet Base in Hatagaya, Shibuya City</h2>

<p>Hatagaya is a neighborhood within Shibuya City, but it does not feel like the area around Shibuya Station. The streets are more residential, and the atmosphere is calmer than Tokyo’s busiest entertainment districts. This distinction is important when choosing accommodation. Some travelers want to stay directly in a crowded center; others prefer to visit major areas during the day and return to a quieter local neighborhood at night.</p>

<p>Izumian is about a 12-minute walk from Hatagaya Station. From there, travelers can reach Shinjuku and connect to other parts of Tokyo. Exact journey times vary by route, transfer, and time of day, so the property should not be described as being “minutes from everywhere.” The practical advantage is that a couple can use Hatagaya as a local base while still accessing major transport connections.</p>

<p>A convenience store is about one minute from the property, which is useful for drinks, breakfast items, and small necessities. Hatagaya Shopping Street can also be part of the stay. Rather than treating the neighborhood only as a place to sleep, couples can walk through local streets and experience a part of Tokyo that is less dominated by large tourist facilities.</p>

<h2>Sleeping on Futons and Using the Tatami Space</h2>

<p>Izumian uses futon bedding on tatami rather than conventional hotel beds. For some couples, this is one of the main reasons to choose a traditional-style private house. It creates a distinctly Japanese sleeping arrangement and allows the room to remain flexible during the day.</p>

<p>Guests should also understand the practical differences. Sleeping close to floor level may not suit everyone. People who strongly prefer a high bed, a thick Western mattress, or easy standing access should consider that before booking. The experience can be comfortable for travelers who are used to firmer bedding, but it is not identical to a hotel bed.</p>

<p>For two guests, futons can be arranged without using the full capacity of the house. This leaves more room for bags and daily movement. It also makes the property better suited to a couple than to four adults with large luggage. The maximum capacity is four, but two guests have the clearest balance between privacy, usable space, and ease of movement.</p>

<h2>Interior Features Couples Should Know Before Booking</h2>

<p>The house includes a wooden spiral staircase connecting the two floors. It is a distinctive part of the interior, but it also requires care. Guests carrying large suitcases may find the staircase less convenient than a standard hotel lift or broad staircase. It may also be unsuitable for people with mobility concerns.</p>

<p>Some parts of the house have low ceilings. This is part of the character of an older-style compact property, but taller guests should be aware of it. Izumian is not barrier-free, and it should not be described as suitable for every traveler. A couple should consider whether both people are comfortable with stairs, futon sleeping, and the proportions of a traditional-style house.</p>

<p>The black-and-wood interior gives the house a clear visual identity. Tatami, futons, the spiral staircase, and the private-house atmosphere are more important to the experience than hotel-style services. Couples looking for daily housekeeping, a front desk, room service, or a large modern lobby should choose a hotel instead. Izumian is designed around private use and self-directed stays.</p>

<h2>Who This Tokyo Accommodation May Suit</h2>

<p>Izumian may suit couples who value privacy, want to stay in a quieter part of Tokyo, and are interested in a traditional-style residential setting. It can also work well for travelers who plan full days in central Tokyo but prefer a less crowded environment in the evening.</p>

<p>It may be especially relevant for couples who want:</p>

<ul>
<li>exclusive use of a whole private house;</li>
<li>tatami and futon sleeping rather than a standard hotel bed;</li>
<li>a local neighborhood within Shibuya City;</li>
<li>access to Shinjuku without staying in Shinjuku itself;</li>
<li>a compact property that is more comfortable for two than for a larger group.</li>
</ul>

<p>The house may not suit couples who require step-free access, dislike futons, need a large bedroom, or expect full hotel services. It may also be inconvenient for travelers with several oversized suitcases because of the compact layout and spiral staircase. Setting these expectations clearly is more useful than presenting the property as suitable for everyone.</p>

<h2>Planning a Couple’s Stay in Tokyo from Hatagaya</h2>

<p>A practical way to use Izumian is to treat it as a calm home base. A couple can leave in the morning for Shinjuku, Shibuya, or another part of Tokyo, then return to Hatagaya for a quieter evening. The nearby convenience store helps with simple purchases, while the local shopping street offers a more residential view of the city.</p>

<p>Because the house is private, couples can organize their trip at their own pace. There is no shared guest area and no need to adjust to another group inside the property. This is useful for different travel routines: one person may want an early start while the other needs more time, or the couple may want to review routes and reservations in a private space.</p>

<p>The location should be understood accurately. Izumian is in Hatagaya, not beside Shibuya Station, and not in Shinjuku. Travelers who want to step outside directly into a major nightlife district may prefer another area. Couples who want a quieter neighborhood and are comfortable walking around 12 minutes from the station may find the trade-off reasonable.</p>

<h2>Maximum Capacity and the Best Use of the House</h2>

<p>The official maximum capacity is four guests. However, maximum capacity does not always equal the most comfortable occupancy. Izumian is recommended for two to three guests, and a couple of two has the most space relative to the house’s compact layout.</p>

<p>For two people, the property can function as more than a sleeping room. There is room to keep personal belongings organized, use the tatami area without filling it entirely with bedding, and move between floors more easily. This is why the same property that may feel compact for four adults can feel more suitable for a couple.</p>

<p>Travelers should still review their own needs. A couple with large equipment, multiple suitcases, or accessibility requirements may prefer a larger modern property. A couple traveling lightly and interested in a private Japanese-style stay is more closely matched to what Izumian offers.</p>

<h2>Book Izumian for Two Guests</h2>

<p>Izumian offers Tokyo accommodation for couples who prefer a private traditional-style house in a quiet Hatagaya neighborhood. It combines exclusive use, tatami, futon bedding, a distinctive wooden spiral staircase, and access to central Tokyo through Hatagaya Station.</p>

<p>Before booking, confirm that both guests are comfortable with futons, stairs, low-ceiling areas, and a compact layout. For two people who value privacy and a local atmosphere, Izumian can provide a practical alternative to a standard hotel room.</p>

<p><a href="https://airhost113589.airhost.co/ja/houses/565943"><strong>Check availability and book Izumian through the official booking page.</strong></a></p>
""".strip()


def now_jst() -> datetime:
    return datetime.now(JST)


def clean_text(value: str) -> str:
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


def word_count(value: str) -> int:
    return len(
        re.findall(
            r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?",
            clean_text(value),
        )
    )


def admin_base_url() -> str:
    parsed = urlparse(WP_URL)

    return (
        f"{parsed.scheme}://{parsed.netloc}"
    )


def validate() -> dict[str, Any]:
    article_text = clean_text(
        CONTENT
    )

    article_lower = article_text.lower()
    title_lower = TITLE.lower()

    checks = {
        "title_length_45_to_65": (
            45 <= len(TITLE) <= 65
        ),
        "meta_length_140_to_165": (
            140
            <= len(META_DESCRIPTION)
            <= 165
        ),
        "word_count_1200_to_1700": (
            1200
            <= word_count(CONTENT)
            <= 1700
        ),
        "primary_keyword_in_title": (
            PRIMARY_KEYWORD
            in title_lower
        ),
        "primary_keyword_in_article": (
            PRIMARY_KEYWORD
            in article_lower
        ),
        "two_guest_focus": any(
            phrase in article_lower
            for phrase in [
                "two guests",
                "two people",
                "couple of two",
            ]
        ),
        "hatagaya_present": (
            "hatagaya"
            in article_lower
        ),
        "maximum_four_disclosed": (
            "maximum capacity is four"
            in article_lower
        ),
        "recommended_occupancy_disclosed": (
            "recommended for two to three"
            in article_lower
        ),
        "futon_present": (
            "futon"
            in article_lower
        ),
        "tatami_present": (
            "tatami"
            in article_lower
        ),
        "spiral_staircase_present": (
            "spiral staircase"
            in article_lower
        ),
        "low_ceiling_present": (
            "low ceiling"
            in article_lower
        ),
        "booking_link_present": (
            BOOKING_URL
            in CONTENT
        ),
        "no_h1_in_body": (
            "<h1"
            not in CONTENT.lower()
        ),
    }

    failed = [
        name
        for name, passed
        in checks.items()
        if not passed
    ]

    return {
        "passed": not failed,
        "failed_checks": failed,
        "checks": checks,
        "title_length": len(TITLE),
        "meta_length": len(
            META_DESCRIPTION
        ),
        "word_count": word_count(
            CONTENT
        ),
    }


def fetch_source_post(
    auth: tuple[str, str],
) -> dict[str, Any]:

    response = requests.get(
        (
            f"{WP_URL}/wp-json/wp/v2/posts/"
            f"{SOURCE_POST_ID}"
        ),
        params={
            "context": "edit",
            "_fields": (
                "id,title,link,featured_media,"
                "categories,tags"
            ),
        },
        auth=auth,
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


def find_existing_draft(
    auth: tuple[str, str],
) -> dict[str, Any] | None:

    response = requests.get(
        f"{WP_URL}/wp-json/wp/v2/posts",
        params={
            "context": "edit",
            "status": "draft",
            "slug": SLUG,
            "per_page": 10,
            "_fields": (
                "id,title,slug,status,link"
            ),
        },
        auth=auth,
        timeout=30,
    )

    response.raise_for_status()

    posts = response.json()

    if posts:
        return posts[0]

    return None


def main() -> int:

    if not WP_USER:
        raise RuntimeError(
            "WP_USER is not set"
        )

    if not WP_APP_PASSWORD:
        raise RuntimeError(
            "WP_APP_PASSWORD is not set"
        )

    validation = validate()

    print(
        "[INFO] Title length:",
        validation["title_length"],
    )

    print(
        "[INFO] Meta length:",
        validation["meta_length"],
    )

    print(
        "[INFO] Word count:",
        validation["word_count"],
    )

    if not validation["passed"]:
        raise RuntimeError(
            "Draft validation failed: "
            + ", ".join(
                validation[
                    "failed_checks"
                ]
            )
        )

    auth = (
        WP_USER,
        WP_APP_PASSWORD,
    )

    print(
        "[INFO] Fetching source post:",
        SOURCE_POST_ID,
    )

    source = fetch_source_post(
        auth
    )

    payload: dict[str, Any] = {
        "title": TITLE,
        "slug": SLUG,
        "status": "draft",
        "content": CONTENT,
        "excerpt": META_DESCRIPTION,
    }

    featured_media = int(
        source.get(
            "featured_media",
            0,
        )
        or 0
    )

    if featured_media:
        payload["featured_media"] = (
            featured_media
        )

    categories = source.get(
        "categories",
        [],
    )

    if categories:
        payload["categories"] = (
            categories
        )

    tags = source.get(
        "tags",
        [],
    )

    if tags:
        payload["tags"] = tags

    existing = find_existing_draft(
        auth
    )

    if existing:
        post_id = existing["id"]

        print(
            "[INFO] Updating existing draft:",
            post_id,
        )

        response = requests.post(
            (
                f"{WP_URL}/wp-json/"
                f"wp/v2/posts/{post_id}"
            ),
            json=payload,
            auth=auth,
            timeout=60,
        )

        action = "updated_existing_draft"

    else:
        print(
            "[INFO] Creating new WordPress draft"
        )

        response = requests.post(
            (
                f"{WP_URL}/wp-json/"
                "wp/v2/posts"
            ),
            json=payload,
            auth=auth,
            timeout=60,
        )

        action = "created_new_draft"

    if response.status_code >= 400:
        raise RuntimeError(
            "WordPress API error "
            f"{response.status_code}: "
            f"{response.text[:1500]}"
        )

    result = response.json()

    post_id = result.get("id")

    edit_url = (
        f"{admin_base_url()}/wp-admin/"
        f"post.php?post={post_id}&action=edit"
    )

    LOCAL_HTML_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    LOCAL_HTML_FILE.write_text(
        CONTENT,
        encoding="utf-8",
    )

    output = {
        "generated_at": (
            now_jst().isoformat(
                timespec="seconds"
            )
        ),
        "action": action,
        "wordpress_status": (
            result.get("status")
        ),
        "draft_post_id": post_id,
        "draft_title": TITLE,
        "draft_slug": (
            result.get("slug")
        ),
        "edit_url": edit_url,
        "source_post_id": (
            SOURCE_POST_ID
        ),
        "source_post_unchanged": True,
        "cron_changed": False,
        "validation": validation,
    }

    RESULT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    RESULT_FILE.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print(
        "===== WORDPRESS DRAFT CREATED ====="
    )

    print(
        "処理:",
        action,
    )

    print(
        "下書きID:",
        post_id,
    )

    print(
        "状態:",
        result.get("status"),
    )

    print(
        "タイトル:",
        TITLE,
    )

    print(
        "slug:",
        result.get("slug"),
    )

    print(
        "記事語数:",
        validation["word_count"],
    )

    print(
        "編集URL:",
        edit_url,
    )

    print(
        "元の記事946:",
        "変更なし",
    )

    print(
        "自動投稿cron:",
        "変更なし・停止中",
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
