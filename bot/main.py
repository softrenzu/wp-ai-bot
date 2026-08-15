import json
import os
import re
import time
import unicodedata
from typing import Optional

import requests

from image_featured import attach_featured_image_from_drive
from templates import get_static_templates_text, get_article_ng_checklist
from local_news import LocalNewsFetcher
from past_titles_db import (
    init_db,
    add_title,
    find_similar_titles,
    fetch_recent_titles,
)

WP_BASE_URL = os.environ.get("WP_URL")
WP_USER = os.environ.get("WP_USER")
WP_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD")
WP_POST_STATUS = os.environ.get("WP_POST_STATUS", "draft")

if not WP_BASE_URL:
    raise RuntimeError("WP_URL is not set")

WP_POSTS_URL = WP_BASE_URL.rstrip("/") + "/wp-json/wp/v2/posts"
TOPIC = os.environ.get("TOPIC", "").strip()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")

# 予約URL（AirHost直販ページ）
BOOKING_URL = "https://airhost113589.airhost.co/ja/houses/565943"

# Instagram / X 連携用：直近の投稿情報を保存するファイル
LAST_POST_FILE = "/secrets/last_post.json"

# アクセス分析フィードバックの保存先
# Docker上では /secrets がホストの ./secrets にマウントされる想定
PROMPT_FEEDBACK_FILE = os.environ.get("PROMPT_FEEDBACK_FILE", "/secrets/prompt_feedback.json")


def _feedback_candidate_paths() -> list[str]:
    paths = [
        PROMPT_FEEDBACK_FILE,
        "/secrets/prompt_feedback.json",
        "secrets/prompt_feedback.json",
        "prompt_feedback.json",
        "bot/prompt_feedback.json",
    ]
    result = []
    for p in paths:
        if p and p not in result:
            result.append(p)
    return result


def load_prompt_feedback() -> str:
    """
    過去記事のアクセス分析結果を読み込み、記事生成プロンプトに差し込む。
    ファイルがない場合は安全にデフォルト指示を返す。
    """
    data = None
    used_path = None

    for path in _feedback_candidate_paths():
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                used_path = path
                break
        except Exception as e:
            print(f"[WARN] prompt feedback load failed: {path}: {e}")

    if not isinstance(data, dict):
        return (
            "No access-analysis feedback is available yet."
            "施設紹介の繰り返しを避け、1記事1テーマで検索意図に答える記事にしてください。"
            "渋谷、渋谷区、新宿近く、古民家、一棟貸切、子連れ、長期滞在などの検索語を自然に使ってください。"
        )

    parts = []
    if used_path:
        parts.append(f"Feedback file: {used_path}")

    if data.get("updated_at"):
        parts.append(f"Updated at: {data.get('updated_at')}")

    if data.get("summary"):
        parts.append(f"Summary: {data.get('summary')}")

    good_patterns = data.get("good_patterns") or []
    if good_patterns:
        parts.append("Positive performance patterns:")
        parts.extend(f"- {x}" for x in good_patterns)

    bad_patterns = data.get("bad_patterns") or []
    if bad_patterns:
        parts.append("Patterns to avoid:")
        parts.extend(f"- {x}" for x in bad_patterns)

    if data.get("next_prompt_instruction"):
        parts.append("Instruction for the next article:")
        parts.append(data.get("next_prompt_instruction"))

    return "\n".join(parts).strip() or (
        "No access-analysis feedback is available yet."
        "1記事1テーマで検索意図に答える記事にしてください。"
    )


def build_system_prompt() -> str:
    feedback_text = load_prompt_feedback()

    return f"""
You are the official blog writer for Izumian, a private traditional-style accommodation in Hatagaya, Shibuya City, Tokyo.

Your job is to write English WordPress blog articles that help international travelers find a quiet, private place to stay in Shibuya City, Tokyo.

[Output format rules]
- Write directly in WordPress-ready HTML.
- Write the article title, headings, and body in natural English.
- Do not write Japanese body text, except for the property name "泉庵 Izumian" when needed.
- Do not use Markdown syntax such as ##, **, or code fences.
- Use <h2>...</h2> for headings.
- Use <p>...</p> for paragraphs.
- Use <a href="...">...</a> for links.
- Use <strong>...</strong> only when emphasis is useful.

[Access-analysis feedback from past articles]
{feedback_text}

[SEO strategy]
- The primary SEO focus is Shibuya / Shibuya City / Tokyo.
- Do not make Hatagaya the main SEO keyword in titles.
- Mention Hatagaya only as the accurate neighborhood inside Shibuya City.
- Prioritize English search phrases such as:
  - private house in Shibuya
  - traditional house stay in Tokyo
  - family stay in Shibuya City
  - quiet stay in Shibuya
  - long stay accommodation in Tokyo
  - private rental near Shinjuku and Shibuya
- Do not imply that Izumian is next to Shibuya Station.
- Describe it accurately as a quiet local stay in Shibuya City.

[Writing rules]
1. Use only real information about Izumian and actual guest impressions.
2. Do not invent facilities, activities, events, or experiences.
3. Do not create mechanical seasonal articles such as "spring version" or "summer version" unless there is a real reason.
4. Always include the booking CTA at the end, linking to {BOOKING_URL}.
5. Mention Izumian's real characteristics naturally: black-and-wood interior, wooden spiral staircase, tatami, futon sleeping style, low ceiling in parts, and private-house atmosphere.
6. Do not repeat the same facility introduction every time.
7. Start by answering the traveler's search intent, then introduce Izumian as a relevant option.
8. Keep the tone practical, calm, and useful for travelers.

[Real property information]
- Izumian is a two-story renovated traditional-style private house in Hatagaya, Shibuya City, Tokyo.
- It is a private rental for one group per day.
- Maximum capacity is 4 guests; recommended for 2 to 3 guests.
- It has black-and-wood interiors, a wooden spiral staircase, tatami, futon bedding, and some low-ceiling areas.
- A convenience store is about 1 minute away.
- Hatagaya Station is about a 12-minute walk.
- It should be described as a quiet local base within Shibuya City, not as a property beside Shibuya Station.
- Airbnb rating: 4.77, with communication 5.0 and check-in 4.9.
- Official booking page: {BOOKING_URL}

[Real nearby places that may be mentioned]
- Nejishiki, a ramen shop known for chicken-based soup.
- Gato, a cafe with matcha and sandwiches.
- Hatagaya Shopping Street.
- 7-Eleven within a short walk.
- Shimokitazawa, a few train stops away.
- Shinjuku and Shibuya, reachable within about 30 minutes depending on route and timing.

[CTA to include at the end of every article]
<h2>Book Your Stay at Izumian</h2>
<p>Izumian is a private traditional-style house in Hatagaya, Shibuya City, available for one group per day.<br>
Enjoy a quiet Tokyo stay with the feeling of living like a local.</p>
<p><a href="{BOOKING_URL}" target="_blank" rel="noopener">▶ Check availability and book directly here</a></p>
""".strip()

def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9 -]+", "", text)
    text = text.lower().strip().replace(" ", "-")
    text = re.sub(r"-+", "-", text)
    return text or "post"


def call_chatgpt(prompt: str, max_tokens: int = 1024, temperature: float = 0.7) -> str:
    url = "https://api.openai.com/v1/chat/completions"
    for attempt in range(5):
        try:
            resp = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": OPENAI_MODEL,
                    "messages": [
                        {"role": "system", "content": build_system_prompt()},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                time.sleep(1)
                return resp.json()["choices"][0]["message"]["content"].strip()
            if resp.status_code == 429:
                wait = 2 ** attempt
                print(f"[RETRY] 429 wait {wait}s")
                time.sleep(wait)
                continue
            resp.raise_for_status()
        except requests.exceptions.Timeout:
            wait = 2 ** attempt
            print(f"[RETRY] timeout wait {wait}s")
            time.sleep(wait)
        except Exception as e:
            print(f"[ERROR] {e}")
            break
    return "渋谷の古民家民泊「泉庵」で過ごす、本物の東京滞在"


def clean_markdown_residue(content: str) -> str:
    """AIが万一Markdown記法を混入させた場合の保険として除去する。"""
    content = re.sub(r"^```(?:html)?\s*", "", content.strip())
    content = re.sub(r"\s*```$", "", content)
    content = re.sub(r"^####\s+(.+)$", r"<h4>\1</h4>", content, flags=re.MULTILINE)
    content = re.sub(r"^###\s+(.+)$", r"<h3>\1</h3>", content, flags=re.MULTILINE)
    content = re.sub(r"^##\s+(.+)$", r"<h2>\1</h2>", content, flags=re.MULTILINE)
    content = re.sub(r"^#\s+(.+)$", r"<h2>\1</h2>", content, flags=re.MULTILINE)
    content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", content)
    return content.strip()


def is_ng_article(content: str) -> bool:
    ng_words = get_article_ng_checklist()
    for word in ng_words:
        if word in content:
            print(f"[NG] 記事にNGワード「{word}」が含まれています。再生成します。")
            return True
    if BOOKING_URL not in content:
        print("[NG] 予約URLが記事に含まれていません。再生成します。")
        return True
    if re.search(r"^##\s", content, flags=re.MULTILINE):
        print("[NG] Markdownの見出し記法が含まれています。再生成します。")
        return True
    return False


def generate_theme(local_news_context: str, static_templates_text: str) -> str:
    recent = fetch_recent_titles()
    past_titles_text = "\n".join(f"- {title}" for _, title in recent) if recent else "(No previous titles yet)"
    feedback_text = load_prompt_feedback()

    prompt = f"""
Create one English blog title for Izumian.

[Previously used titles. Do not repeat similar titles.]
{past_titles_text}

[Local news or local context for today]
{local_news_context}

[Property information and allowed nearby places]
{static_templates_text}

[Search Console feedback and SEO direction]
{feedback_text}

[Title requirements]
- Output only one English title.
- Length: 45 to 75 English characters.
- Use Shibuya, Shibuya City, or Tokyo as the main SEO focus.
- Do not make Hatagaya the main keyword, but you may mention it if needed for accuracy.
- Include one clear travel intent, such as private house, traditional house stay, family stay, long stay, quiet local stay, or near Shinjuku and Shibuya.
- Do not imply that the property is next to Shibuya Station.
- Do not invent facilities, events, or activities.
- Do not use Markdown, quotation marks, bullets, or explanation.
""".strip()

    title = call_chatgpt(prompt, max_tokens=128, temperature=0.8)
    title = re.sub(r"^#+\s*", "", title.strip())
    title = re.sub(r"\*\*", "", title)
    title = title.strip("「」\"' ")
    return title

def generate_article(theme: str, local_news_context: str, static_templates_text: str) -> str:
    feedback_text = load_prompt_feedback()

    prompt = f"""
Write an English WordPress blog article for Izumian.

[Article theme]
{theme}

[Local context for today]
{local_news_context}

[Property information and allowed nearby places]
{static_templates_text}

[Search Console feedback and SEO direction]
{feedback_text}

[Article requirements]
- Output format: HTML only.
- Write in natural English.
- Do not write Japanese body text, except for "泉庵 Izumian" if needed.
- Do not use Markdown.
- Use <h2>...</h2> for headings and <p>...</p> for paragraphs.
- Length: 700 to 1,100 English words, excluding HTML tags.
- Structure: 3 to 4 <h2> sections, a short conclusion, and the booking CTA.
- The first half must answer the traveler's search intent clearly.
- The second half must naturally explain why Izumian fits that need.
- Use Shibuya / Shibuya City / Tokyo as the main SEO focus.
- Mention Hatagaya only as the accurate neighborhood inside Shibuya City.
- Do not imply that Izumian is next to Shibuya Station.
- Do not repeat the same generic facility introduction in every article.
- Refer to actual guest impressions at least once, without inventing fake quotes.
- Naturally include real Izumian features such as black-and-wood interiors, spiral staircase, tatami, futon bedding, private-house atmosphere, and some low-ceiling areas.
- Do not mention nonexistent facilities, services, experiences, or events.
- Include the following CTA exactly at the end:

<h2>Book Your Stay at Izumian</h2>
<p>Izumian is a private traditional-style house in Hatagaya, Shibuya City, available for one group per day.<br>
Enjoy a quiet Tokyo stay with the feeling of living like a local.</p>
<p><a href="{BOOKING_URL}" target="_blank" rel="noopener">▶ Check availability and book directly here</a></p>

[Output]
Output only the English HTML body. Do not include <html> or <body> tags. Do not use code fences.
""".strip()

    article = ""
    for attempt in range(3):
        article = call_chatgpt(prompt, max_tokens=2048, temperature=0.7)
        article = clean_markdown_residue(article)
        if not is_ng_article(article):
            return article
        print(f"[RETRY] Article regeneration attempt {attempt + 1}")
        prompt += "\n\nThe previous output failed validation. Use HTML only, do not use Markdown, and include the booking CTA exactly."

    print("[WARN] Article failed validation 3 times. Using the last generated result.")
    return article

def post_to_wordpress(title: str, content: str) -> Optional[dict]:
    slug = slugify(title)
    payload = {
        "title": title,
        "content": content,
        "status": WP_POST_STATUS,
        "slug": slug,
    }
    try:
        resp = requests.post(
            WP_POSTS_URL,
            json=payload,
            auth=(WP_USER, WP_APP_PASSWORD),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[ERROR] WordPress投稿失敗: {e}")
        return None


def save_last_post_info(post_id: int, title: str, post_link: str, image_url: Optional[str]):
    """
    Instagram / X 連携用に、直近の投稿情報を保存する。
    main_ig.py / main_x.py 等から読み込まれる。
    """
    info = {
        "post_id": post_id,
        "title": title,
        "post_link": post_link,
        "image_url": image_url,
        "booking_url": BOOKING_URL,
    }
    try:
        os.makedirs(os.path.dirname(LAST_POST_FILE), exist_ok=True)
        with open(LAST_POST_FILE, "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
        print(f"[INFO] 投稿情報を保存しました: {LAST_POST_FILE}")
    except Exception as e:
        print(f"[WARN] 投稿情報の保存に失敗: {e}")


def run_once():
    """
    本番エントリーポイント。main_wp.py から呼ばれる。
    1回の実行で1記事を生成して投稿し、画像オーバーレイを焼き、
    Instagram/X 連携用の情報を保存する。
    """
    print("[START] 泉庵 Izumian ブログ自動生成")

    init_db()

    # 1. 素材取得
    fetcher = LocalNewsFetcher()
    local_news_context = fetcher.build_local_news_context()
    static_templates_text = get_static_templates_text()

    print(f"[INFO] ローカルニュース取得:\n{local_news_context[:200]}...")

    # 2. テーマ生成
    if TOPIC:
        theme = TOPIC
        print(f"[INFO] 環境変数TOPICを使用: {theme}")
    else:
        theme = generate_theme(local_news_context, static_templates_text)
        print(f"[INFO] 生成テーマ: {theme}")

    # 3. 重複チェック
    similar = find_similar_titles(theme)
    if similar:
        print(f"[WARN] 類似タイトルあり: {similar}")
        theme = generate_theme(local_news_context, static_templates_text)
        print(f"[INFO] 再生成テーマ: {theme}")

    # 4. 記事生成
    article = generate_article(theme, local_news_context, static_templates_text)
    print(f"[INFO] 記事生成完了（{len(article)}文字）")

    # 5. WordPress投稿
    result = post_to_wordpress(theme, article)
    if not result:
        print("[ERROR] WordPress投稿に失敗しました")
        return

    post_id = result.get("id")
    post_link = result.get("link", "")
    print(f"[OK] 投稿完了: ID={post_id}, タイトル={theme}, URL={post_link}")

    # 6. タイトルをDBに保存
    add_title(theme)

    # 7. アイキャッチ画像（タイトル＋予約URLを焼き込んだ画像）
    image_url = None
    try:
        image_url = attach_featured_image_from_drive(
            post_id=post_id,
            post_title=theme,
            post_link=BOOKING_URL,
        )
        print(f"[OK] アイキャッチ画像設定完了: {image_url}")
    except Exception as e:
        print(f"[WARN] アイキャッチ画像の設定失敗（スキップ）: {e}")

    # 8. Instagram / X 連携用に投稿情報を保存
    save_last_post_info(post_id, theme, post_link, image_url)


if __name__ == "__main__":
    run_once()
