#!/usr/bin/env python3

import os
import sys
from urllib.parse import urlparse

import requests


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

POST_ID = 989

BOOKING_URL = (
    "https://airhost113589.airhost.co/"
    "ja/houses/565943"
)


def main() -> int:
    if not WP_USER or not WP_APP_PASSWORD:
        raise RuntimeError(
            "WP_USER or WP_APP_PASSWORD is not set"
        )

    auth = (
        WP_USER,
        WP_APP_PASSWORD,
    )

    response = requests.get(
        (
            f"{WP_URL}/wp-json/"
            f"wp/v2/posts/{POST_ID}"
        ),
        params={
            "context": "edit",
        },
        auth=auth,
        timeout=30,
    )

    response.raise_for_status()

    post = response.json()

    current_status = post.get(
        "status",
        "",
    )

    content = (
        post.get("content") or {}
    ).get(
        "raw",
        "",
    )

    if not content:
        content = (
            post.get("content") or {}
        ).get(
            "rendered",
            "",
        )

    if BOOKING_URL not in content:
        raise RuntimeError(
            "Direct-booking link is missing "
            "from post 989"
        )

    if current_status == "publish":
        print(
            "[INFO] Post 989 is already published"
        )

        published = post

    else:
        print(
            "[INFO] Publishing post 989"
        )

        publish_response = requests.post(
            (
                f"{WP_URL}/wp-json/"
                f"wp/v2/posts/{POST_ID}"
            ),
            json={
                "status": "publish"
            },
            auth=auth,
            timeout=60,
        )

        if publish_response.status_code >= 400:
            raise RuntimeError(
                "WordPress publish error "
                f"{publish_response.status_code}: "
                f"{publish_response.text[:1000]}"
            )

        published = publish_response.json()

    parsed = urlparse(WP_URL)

    edit_url = (
        f"{parsed.scheme}://{parsed.netloc}"
        f"/wp-admin/post.php?"
        f"post={POST_ID}&action=edit"
    )

    print()
    print(
        "===== COUPLES ARTICLE PUBLISHED ====="
    )

    print(
        "投稿ID:",
        published.get("id")
    )

    print(
        "状態:",
        published.get("status")
    )

    print(
        "タイトル:",
        (
            published.get("title") or {}
        ).get(
            "rendered",
            "",
        )
    )

    print(
        "公開URL:",
        published.get("link")
    )

    print(
        "編集URL:",
        edit_url
    )

    print(
        "直接予約リンク:",
        BOOKING_URL
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
