import os
import re
import time
import unicodedata
from typing import Optional

import requests
from image_featured import attach_featured_image_from_drive
from templates import get_static_templates_text
from local_news import LocalNewsFetcher
from past_titles_db import (
    init_db,
    add_title,
    find_similar_titles,
    fetch_recent_titles,
)

# =========================================================
# WordPress 設定
# =========================================================

WP_BASE_URL = os.environ.get("WP_URL")
WP_USER = os.environ.get("WP_USER")
WP_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD")
WP_POST_STATUS = os.environ.get("WP_POST_STATUS", "draft")

if not WP_BASE_URL:
    raise RuntimeError("WP_URL is not set")

WP_POSTS_URL = WP_BASE_URL.rstrip("/") + "/wp-json/wp/v2/posts"
TOPIC = os.environ.get("TOPIC", "").strip()

# =========================================================
# OpenAI 設定
# =========================================================

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")

# =========================================================
# Utility
# =========================================================

def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9 -]+", "", text)
    text = text.lower().strip().replace(" ", "-")
    text = re.sub(r"-+", "-", text)
    return text or "post"

# =========================================================
# ChatGPT 呼び出し
# =========================================================

def call_chatgpt(prompt: str, max_tokens=1024, temperature=0.7) -> str:
    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPENAI_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "あなたは民泊運営と旅行者ニーズに精通した日本語プロライターです。"
                },
                {
                    "role": "user",
                    "content": prompt
                },
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()

# =========================================================
# テーマ生成（元の詳細プロンプト）
# =========================================================

def generate_theme(local_news_context: str, static_templates_text: str) -> str:
    recent = fetch_recent_titles()
    past_titles_text = "\n".join(f"- {title}" for _, title in recent)

    prompt = f"""
あなたは「渋谷区・幡ヶ谷エリア」専門の民泊集客コンサルタント兼ローカルメディア編集長です。

目的：
- 幡ヶ谷エリアの民泊に泊まりに来る旅行者向けに、
  そのまま記事タイトルとして使える日本語タイトルを1つ作ること

必ず守る条件：
- 「幡ヶ谷」または「渋谷区」を必ず含める
- 民泊・宿泊・滞在に関係する内容にする
- 質問文（〜ですか？等）にしない
- 指示文・AI向けメタ表現を書かない
- 箇条書きや番号は禁止
- 28〜34文字程度
- タイトル文字列のみを1行で出力する

今日のローカル情報：
{local_news_context}

テーマの型（参考）：
{static_templates_text}

過去に投稿済みのタイトル：
{past_titles_text}

上記を踏まえて、新しい切り口のタイトルを1つだけ出力してください。
""".strip()

    for _ in range(5):
        candidate = call_chatgpt(prompt, max_tokens=128)
        candidate = candidate.splitlines()[0].strip()

        if "幡ヶ谷" not in candidate and "渋谷区" not in candidate:
            continue
        if find_similar_titles(candidate):
            continue
        return candidate

    return "幡ヶ谷民泊で快適に過ごすための滞在ガイド"

# =========================================================
# 記事生成（元の詳細プロンプト）
# =========================================================

def generate_article(theme: str) -> str:
    prompt = f"""
あなたは日本語の旅行・民泊専門ライターです。

次のテーマで、幡ヶ谷エリアの民泊に泊まる旅行者向けに
ブログ記事本文のみを書いてください。

【テーマ】
{theme}

ルール：
- タイトルは本文に含めない
- 箇条書きは使わない
- 「問題」「結論」などのメタ表現を書かない
- 構成は「導入 → 見出し3つ → まとめ」
- 見出しは Markdown の ## を使用
- です・ます調
- 1200〜1600文字程度
""".strip()

    return call_chatgpt(prompt, max_tokens=3500, temperature=0.8)

# =========================================================
# メイン処理
# =========================================================

def run_once():
    init_db()

    if TOPIC:
        theme = TOPIC
    else:
        fetcher = LocalNewsFetcher()
        local_news_context = fetcher.build_local_news_context()
        static_templates_text = get_static_templates_text()
        theme = generate_theme(local_news_context, static_templates_text)

    body = generate_article(theme)

    resp = requests.post(
        WP_POSTS_URL,
        json={
            "title": theme,
            "content": body,
            "status": WP_POST_STATUS,
            "slug": slugify(theme),
        },
        auth=(WP_USER, WP_APP_PASSWORD),
    )
    resp.raise_for_status()
    post = resp.json()

    attach_featured_image_from_drive(
        post_id=post["id"],
        post_title=theme,
        post_link=post.get("link"),
    )

    add_title(theme)

if __name__ == "__main__":
    run_once()
