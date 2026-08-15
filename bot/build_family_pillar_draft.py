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

WP_URL = os.environ.get(
    "WP_URL",
    "https://staytokyo.xyz",
).rstrip("/")

OPENAI_API_KEY = os.environ.get(
    "OPENAI_API_KEY",
    "",
)

OPENAI_MODEL = os.environ.get(
    "OPENAI_MODEL",
    "gpt-4.1-mini",
)

SOURCE_POST_ID = 946

BOOKING_URL = (
    "https://airhost113589.airhost.co/"
    "ja/houses/565943"
)

JSON_OUTPUT = Path(
    "/secrets/family_pillar_draft.json"
)

HTML_OUTPUT = Path(
    "/app/drafts/family-pillar-draft.html"
)

TEXT_OUTPUT = Path(
    "/app/drafts/family-pillar-draft.txt"
)

PRIMARY_KEYWORD = (
    "tokyo accommodation for family of 4"
)

SECONDARY_KEYWORDS = [
    "tokyo accommodation for 4",
    "where to stay in tokyo with family",
    "where to stay in tokyo family of 4",
    "family accommodation tokyo",
    "family accommodation near shinjuku",
    "private house in tokyo for family",
]


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


def word_count(value: str) -> int:
    return len(
        re.findall(
            r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?",
            clean_html(value),
        )
    )


def fetch_source_post() -> dict[str, Any]:
    response = requests.get(
        (
            f"{WP_URL}/wp-json/wp/v2/posts/"
            f"{SOURCE_POST_ID}"
        ),
        params={
            "_fields": (
                "id,date,modified,link,slug,"
                "title,content,excerpt,status"
            )
        },
        timeout=30,
    )

    response.raise_for_status()

    item = response.json()

    return {
        "id": item.get("id"),
        "date": item.get("date", ""),
        "modified": item.get("modified", ""),
        "link": item.get("link", ""),
        "slug": item.get("slug", ""),
        "status": item.get("status", ""),
        "title": clean_html(
            (item.get("title") or {}).get(
                "rendered",
                "",
            )
        ),
        "content_html": (
            (item.get("content") or {}).get(
                "rendered",
                "",
            )
        ),
        "content_text": clean_html(
            (item.get("content") or {}).get(
                "rendered",
                "",
            )
        ),
        "excerpt": clean_html(
            (item.get("excerpt") or {}).get(
                "rendered",
                "",
            )
        ),
    }


def call_openai(
    system_prompt: str,
    user_prompt: str,
) -> dict[str, Any]:

    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY is not set"
        )

    payload = {
        "model": OPENAI_MODEL,
        "temperature": 0.35,
        "max_tokens": 4000,
        "response_format": {
            "type": "json_object"
        },
        "messages": [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
    }

    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": (
                f"Bearer {OPENAI_API_KEY}"
            ),
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=180,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            "OpenAI API error "
            f"{response.status_code}: "
            f"{response.text[:1000]}"
        )

    result = response.json()

    content = (
        result["choices"][0]["message"]["content"]
    )

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(
            r"\{.*\}",
            content,
            flags=re.DOTALL,
        )

        if not match:
            raise

        return json.loads(match.group(0))


def build_prompts(
    source: dict[str, Any],
) -> tuple[str, str]:

    system_prompt = f"""
You are an SEO editor for Izumian, a private
traditional-style accommodation in Hatagaya,
Shibuya City, Tokyo.

You are preparing a replacement draft for an
existing WordPress post. Do not publish anything.

Write accurate, practical English for international
travelers making an accommodation decision.

The article must not exaggerate location, capacity,
comfort, child safety or facilities.

Return one valid JSON object only.
"""

    user_prompt = f"""
Create a replacement draft for this existing post:

Source post ID: {source["id"]}
Source URL: {source["link"]}
Source title: {source["title"]}

Primary search phrase:
{PRIMARY_KEYWORD}

Related phrases to cover naturally within the same
page, not as separate articles:
{json.dumps(SECONDARY_KEYWORDS, ensure_ascii=False)}

Verified facts:
- Property name: Izumian / 泉庵 Izumian.
- It is in Hatagaya, Shibuya City, Tokyo.
- It is not beside Shibuya Station.
- It is not in Shinjuku.
- Hatagaya Station is about a 12-minute walk.
- It is a renovated two-story private house.
- One group uses the entire house.
- Maximum capacity is four guests.
- Two to three guests is the recommended comfort
  level.
- Four guests can stay, but the article must
  honestly explain that the house is compact.
- Do not describe it as suitable for five guests
  or large groups.
- Do not call it a hotel.
- Interior characteristics include black-and-wood
  styling, tatami, futon bedding, a wooden spiral
  staircase and some low-ceiling areas.
- The spiral staircase and low ceilings should be
  disclosed clearly. Do not claim that the property
  is child-safe, barrier-free or suitable for every
  family.
- A convenience store is about one minute away.
- Hatagaya Shopping Street may be mentioned.
- Access to Shinjuku is convenient, but do not state
  that the property is located in Shinjuku.
- The official booking URL is:
  {BOOKING_URL}

Source article text:
--- SOURCE START ---
{source["content_text"][:14000]}
--- SOURCE END ---

Create JSON with exactly these keys:

{{
  "title": "English SEO title",
  "slug": "lowercase-English-slug",
  "meta_description": "English meta description",
  "search_intent": "One-sentence description",
  "primary_keyword": "{PRIMARY_KEYWORD}",
  "secondary_keywords": [
    "keyword"
  ],
  "html": "Complete WordPress-ready HTML",
  "change_summary": [
    "change"
  ],
  "claims_to_verify": [
    "claim"
  ]
}}

Requirements:
1. Title must be 45 to 65 characters.
2. Put the primary phrase, or a grammatically natural
   close variant, near the beginning of the title.
3. Meta description must be 140 to 165 characters.
4. Article length must be 1,200 to 1,700 English words.
5. Use HTML only in the html field.
6. Do not include an H1 inside the article body.
7. Use H2 and H3 headings.
8. Answer the family-of-four accommodation question
   within the first 150 words.
9. Explain maximum capacity versus recommended comfort
   level clearly.
10. Include a practical suitability section covering:
    sleeping layout, privacy, compact size, futons,
    spiral staircase and low ceilings.
11. Include a section explaining Hatagaya and access
    to Shinjuku accurately.
12. Explain who the property may not suit.
13. Do not use unsupported claims such as:
    best, perfect, safest, luxury, spacious,
    minutes from Shibuya Station, childproof,
    barrier-free or ideal for everyone.
14. Do not invent room dimensions, journey times,
    appliances, prices or nearby attractions.
15. Include one clear booking CTA at the end using:
    {BOOKING_URL}
16. Do not repeat the same introduction in multiple
    sections.
17. Write useful accommodation-selection information
    before promotional language.
18. Do not create fake reviews or guest quotations.
"""

    return system_prompt, user_prompt


def validate_draft(
    draft: dict[str, Any],
) -> dict[str, Any]:

    title = str(
        draft.get("title", "")
    ).strip()

    slug = str(
        draft.get("slug", "")
    ).strip()

    meta = str(
        draft.get("meta_description", "")
    ).strip()

    article_html = str(
        draft.get("html", "")
    ).strip()

    article_text = clean_html(article_html)
    article_lower = article_text.lower()
    title_lower = title.lower()

    checks = {
        "title_present": bool(title),
        "title_length_45_to_65": (
            45 <= len(title) <= 65
        ),
        "slug_valid": bool(
            re.fullmatch(
                r"[a-z0-9]+(?:-[a-z0-9]+)*",
                slug,
            )
        ),
        "meta_length_140_to_165": (
            140 <= len(meta) <= 165
        ),
        "word_count_1200_to_1700": (
            1200 <= word_count(article_html) <= 1700
        ),
        "contains_h2": (
            "<h2" in article_html.lower()
        ),
        "contains_no_h1": (
            "<h1" not in article_html.lower()
        ),
        "family_of_four_intent": any(
            phrase in (
                title_lower + " " + article_lower
            )
            for phrase in [
                "family of 4",
                "family of four",
                "four guests",
                "accommodation for 4",
            ]
        ),
        "maximum_four_stated": any(
            phrase in article_lower
            for phrase in [
                "maximum capacity is four",
                "maximum of four guests",
                "maximum four guests",
                "up to four guests",
            ]
        ),
        "recommended_two_three_stated": any(
            phrase in article_lower
            for phrase in [
                "recommended for two to three",
                "recommended for 2 to 3",
                "best suited to two or three",
                "best suited for two or three",
                "most comfortable for two to three",
            ]
        ),
        "spiral_staircase_stated": (
            "spiral staircase" in article_lower
        ),
        "low_ceiling_stated": (
            "low ceiling" in article_lower
        ),
        "hatagaya_stated": (
            "hatagaya" in article_lower
        ),
        "booking_link_present": (
            BOOKING_URL in article_html
        ),
        "not_for_five_guests": not any(
            phrase in article_lower
            for phrase in [
                "suitable for five",
                "up to five guests",
                "family of five can stay",
            ]
        ),
        "not_called_hotel": not any(
            phrase in article_lower
            for phrase in [
                "izumian hotel",
                "our hotel",
                "this hotel",
            ]
        ),
    }

    failed = [
        name
        for name, passed in checks.items()
        if not passed
    ]

    return {
        "checks": checks,
        "failed_checks": failed,
        "passed": not failed,
        "title_length": len(title),
        "meta_length": len(meta),
        "word_count": word_count(article_html),
    }


def main() -> int:
    print(
        "[INFO] Fetching source post:",
        SOURCE_POST_ID,
    )

    source = fetch_source_post()

    print(
        "[INFO] Source title:",
        source["title"],
    )

    system_prompt, user_prompt = build_prompts(
        source
    )

    print(
        "[INFO] Generating replacement draft "
        f"with {OPENAI_MODEL}..."
    )

    draft = call_openai(
        system_prompt,
        user_prompt,
    )

    validation = validate_draft(
        draft
    )

    output = {
        "version": 1,
        "generated_at": now_jst().isoformat(
            timespec="seconds"
        ),
        "mode": "local_draft_only",
        "wordpress_modified": False,
        "published": False,
        "source_post": {
            "id": source["id"],
            "url": source["link"],
            "title": source["title"],
            "date": source["date"],
            "modified": source["modified"],
            "status": source["status"],
        },
        "target": {
            "primary_keyword": PRIMARY_KEYWORD,
            "secondary_keywords": (
                SECONDARY_KEYWORDS
            ),
        },
        "draft": draft,
        "validation": validation,
    }

    JSON_OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    HTML_OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    JSON_OUTPUT.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    HTML_OUTPUT.write_text(
        str(
            draft.get("html", "")
        ),
        encoding="utf-8",
    )

    TEXT_OUTPUT.write_text(
        "\n".join([
            f"TITLE: {draft.get('title', '')}",
            f"SLUG: {draft.get('slug', '')}",
            "",
            "META DESCRIPTION:",
            str(
                draft.get(
                    "meta_description",
                    "",
                )
            ),
            "",
            "SEARCH INTENT:",
            str(
                draft.get(
                    "search_intent",
                    "",
                )
            ),
            "",
            "VALIDATION:",
            json.dumps(
                validation,
                ensure_ascii=False,
                indent=2,
            ),
            "",
            "ARTICLE:",
            clean_html(
                str(
                    draft.get(
                        "html",
                        "",
                    )
                )
            ),
        ]),
        encoding="utf-8",
    )

    print(
        "[OK] JSON draft:",
        JSON_OUTPUT,
    )

    print(
        "[OK] HTML draft:",
        HTML_OUTPUT,
    )

    print(
        "[OK] Text preview:",
        TEXT_OUTPUT,
    )

    print(
        "[RESULT] Validation passed:",
        validation["passed"],
    )

    print(
        "[RESULT] Failed checks:",
        validation["failed_checks"],
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
