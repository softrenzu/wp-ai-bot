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

# ===============================
# 泉庵 Izumian 固有のシステムプロンプト
# ===============================
SYSTEM_PROMPT = f"""
あなたは東京・渋谷区幡ヶ谷にある古民家民泊「泉庵 Izumian」の公式ブログライターです。

【絶対に守る出力形式】
- 出力は WordPress に直接投稿される HTML 形式で書く
- Markdown記法（## や ** など）は絶対に使わない
- 見出しは <h2>...</h2>、本文は <p>...</p>、リンクは <a href="...">...</a> で書く
- 強調は <strong>...</strong> を使う

【あなたのルール】
1. 施設の実情報・実際のゲストレビューに基づいた記事だけを書く
2. 存在しない体験・架空の施設は絶対に書かない（農業体験・架空イベントなど）
3. 「春の〇〇」「夏の〇〇」という季節変数の機械的な置換はしない
4. 毎回、記事末尾に予約CTA（{BOOKING_URL}）を必ず<a>タグでリンク付きで入れる
5. 泉庵の個性（黒×木インテリア・螺旋階段・布団・天井低め）を自然に盛り込む
6. 実際のゲストの言葉を引用・参考にして説得力を持たせる

【泉庵 Izumian の基本情報】
- 渋谷区幡ヶ谷の2階建てリノベ古民家（一棟貸切・1日1組限定）
- 黒×木インテリア、木製螺旋階段、畳・布団体験可、天井低め
- 定員最大4名（推奨2〜3名）、コンビニ徒歩1分、幡ヶ谷駅徒歩約12分
- Airbnb ★4.77（コミュニケーション5.0、チェックイン4.9）
- 公式予約ページ：{BOOKING_URL}

【実在する周辺スポット（これ以外は書かない）】
- ねじしき（鶏ガラスープのラーメン）/ Gato（抹茶・サンドイッチのカフェ）
- 幡ヶ谷商店街 / セブンイレブン徒歩2分 / 下北沢（電車で数駅）
- 新宿・渋谷（30分以内）

【記事末尾に毎回入れるCTA（このHTMLをそのまま末尾に入れる）】
<h2>泉庵 Izumian のご予約</h2>
<p>泉庵 Izumianは、渋谷区幡ヶ谷の1日1組限定・完全貸切古民家です。<br>
"暮らすような東京滞在"をぜひ体験してみてください。</p>
<p><a href="{BOOKING_URL}" target="_blank" rel="noopener">▶ 公式サイトで空き状況を確認・ご予約はこちら</a></p>
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
                        {"role": "system", "content": SYSTEM_PROMPT},
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
    return "幡ヶ谷の古民家民泊「泉庵」で過ごす、本物の東京滞在"


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
    past_titles_text = "\n".join(f"- {title}" for _, title in recent) if recent else "（まだ記事なし）"

    prompt = f"""
以下の情報を参考に、泉庵 Izumianのブログ記事タイトルを1つ作成してください。

【過去に作成済みのタイトル（重複禁止）】
{past_titles_text}

【今日のローカルニュース・トピック】
{local_news_context}

【参考にすべき施設情報・周辺スポット】
{static_templates_text}

【タイトル生成の条件】
- 28〜40文字
- 「幡ヶ谷」または「渋谷区」を含める
- 泉庵の実際の特徴（古民家・一棟貸切・和風インテリアなど）を自然に反映する
- 架空の体験（農業体験など）を含めない
- 過去タイトルと意味的に重複しないこと
- タイトルのみ出力（##や記号、説明文は不要）
""".strip()

    title = call_chatgpt(prompt, max_tokens=128, temperature=0.8)
    # タイトルのMarkdown記号を除去
    title = re.sub(r"^#+\s*", "", title.strip())
    title = re.sub(r"\*\*", "", title)
    title = title.strip("「」\"' ")
    return title


def generate_article(theme: str, local_news_context: str, static_templates_text: str) -> str:
    prompt = f"""
以下のテーマで、泉庵 Izumianのブログ記事を書いてください。

【テーマ】
{theme}

【今日のローカル情報（参考）】
{local_news_context}

【施設情報・使用可能なスポット】
{static_templates_text}

【記事の条件】
- 出力形式：HTML（Markdownは絶対に使わない）
- 見出しは <h2>...</h2>、本文は <p>...</p> で書く
- 文字数：1,200〜1,800字（HTMLタグを除いて）
- 構成：<h2>3〜4個＋まとめ段落＋予約CTA
- 実際のゲストの声を少なくとも1箇所引用または参照する
- 泉庵固有の特徴（黒×木インテリア・螺旋階段・布団・天井低めなど）を自然に含める
- 存在しない施設・体験は書かない
- 記事末尾に必ず以下の予約CTAをそのまま貼る：

<h2>泉庵 Izumian のご予約</h2>
<p>泉庵 Izumianは、渋谷区幡ヶ谷の1日1組限定・完全貸切古民家です。<br>
"暮らすような東京滞在"をぜひ体験してみてください。</p>
<p><a href="{BOOKING_URL}" target="_blank" rel="noopener">▶ 公式サイトで空き状況を確認・ご予約はこちら</a></p>

【出力】
HTMLの本文のみを出力してください。<html>や<body>タグは不要。コードフェンス（```）も不要。
""".strip()

    article = ""
    for attempt in range(3):
        article = call_chatgpt(prompt, max_tokens=2048, temperature=0.7)
        article = clean_markdown_residue(article)
        if not is_ng_article(article):
            return article
        print(f"[RETRY] 記事再生成 attempt {attempt + 1}")
        prompt += "\n\n※前回の生成でNGがありました。HTML形式を厳守し、Markdownは使わないでください。"

    print("[WARN] NGチェックを3回通過できませんでした。最後の生成結果を使用します。")
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
            post_link=BOOKING_URL,  # 画像下に焼き込むサブテキスト＝予約URL
        )
        print(f"[OK] アイキャッチ画像設定完了: {image_url}")
    except Exception as e:
        print(f"[WARN] アイキャッチ画像の設定失敗（スキップ）: {e}")

    # 8. Instagram / X 連携用に投稿情報を保存
    save_last_post_info(post_id, theme, post_link, image_url)


if __name__ == "__main__":
    run_once()
