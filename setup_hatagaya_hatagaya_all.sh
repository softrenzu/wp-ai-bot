#!/usr/bin/env bash
set -e

# =========================================================
# 幡ヶ谷×民泊 自動投稿ボット 用
# 1) 既存コードのバックアップ
# 2) bot配下コード一式の生成・更新
# 3) docker-compose.yml の差し替え
# =========================================================

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

echo "[INFO] Working directory: $ROOT_DIR"

# ---------------------------------------------------------
# 1. バックアップ作成
# ---------------------------------------------------------
BACKUP_DIR="$ROOT_DIR/backups"
mkdir -p "$BACKUP_DIR"

TS="$(date +%Y%m%d-%H%M%S)"
BACKUP_TAR="$BACKUP_DIR/wp-ai-bot-backup-$TS.tar.gz"

echo "[INFO] Creating backup archive: $BACKUP_TAR"

# bot, docker-compose.yml, .env をバックアップ
tar czf "$BACKUP_TAR" \
  ./bot \
  ./docker-compose.yml \
  ./.env \
  2>/dev/null || true

echo "[INFO] Backup created (if files existed)."

# ---------------------------------------------------------
# 2. bot ディレクトリ & コード生成
# ---------------------------------------------------------
mkdir -p bot

echo "[INFO] Writing bot/requirements.txt ..."
cat > bot/requirements.txt <<'EOF'
requests
beautifulsoup4
EOF

echo "[INFO] Writing bot/templates.py ..."
cat > bot/templates.py <<'EOF'
from textwrap import dedent
from itertools import product


def get_static_templates_text() -> str:
    """
    民泊 × 幡ヶ谷 × 集客 のテーマの「型」を
    コード内で自動的に大量生成してテキスト化する。

    人手でメンテナンスしなくても、多様な切り口が出続けることを想定。
    """

    base_categories = [
        "幡ヶ谷の魅力・街の雰囲気",
        "幡ヶ谷からのアクセス・移動方法",
        "幡ヶ谷周辺の観光スポット",
        "幡ヶ谷周辺の飲食店・グルメ情報",
        "幡ヶ谷での子連れ・家族旅行",
        "幡ヶ谷での一人旅・女性一人旅",
        "幡ヶ谷での長期滞在・ワーケーション",
        "幡ヶ谷民泊と周辺イベントの組み合わせ",
        "幡ヶ谷民泊に泊まるときの不安解消・Q&A",
        "幡ヶ谷民泊を拠点にした東京観光モデルコース",
    ]

    targets = [
        "カップル旅行",
        "子連れファミリー",
        "女性一人旅",
        "男性一人旅",
        "友人グループ",
        "ビジネス出張",
        "長期滞在ワーカー",
        "外国人旅行者",
    ]

    intents = [
        "不安を解消する",
        "宿泊のイメージを具体的に持ってもらう",
        "幡ヶ谷に泊まるメリットを理解してもらう",
        "周辺施設の利便性を伝える",
        "夜の治安や雰囲気を伝える",
        "子連れでも安心できることを伝える",
        "深夜・早朝の移動のしやすさを伝える",
        "飲食店やカフェの充実度を伝える",
        "イベントと合わせた滞在の楽しさを伝える",
    ]

    seasons = [
        "春（花見・新生活シーズン）",
        "夏（夏祭り・海・花火シーズン）",
        "秋（紅葉・連休・行楽シーズン）",
        "冬（年末年始・イルミネーションシーズン）",
        "ゴールデンウィーク",
        "シルバーウィーク",
        "受験・就活シーズン",
        "ライブ・イベント集中シーズン",
    ]

    # 組み合わせで「テーマの型」を大量生成
    patterns = []
    for cat, tgt, it, season in product(base_categories, targets, intents, seasons):
        patterns.append(
            f"- カテゴリ: {cat} / ターゲット: {tgt} / 目的: {it} / 時期: {season}"
        )

    text = dedent(
        f"""
        以下は、幡ヶ谷エリアの民泊集客用ブログ記事で取りうる
        多数の切り口パターンの一部例です。

        それぞれのパターンは、
        - 幡ヶ谷という地名
        - 民泊（宿泊）
        - 誰が泊まるのか（ターゲット）
        - どんな目的・不安・期待を持っているか
        - どの時期に泊まるのか（季節・イベント）

        を組み合わせた「テーマの型」を表しています。

        これらの型を参考にしつつ、
        過去記事と重複しない新しいテーマを1つだけ考えてください。

        テーマの型一覧（抜粋）:
        {chr(10).join(patterns[:400])}

        ※実際には同様のパターンが多数存在すると考えてください。
        """
    ).strip()

    return text
EOF

echo "[INFO] Writing bot/local_news.py ..."
cat > bot/local_news.py <<'EOF'
import datetime
from textwrap import dedent

import requests
from bs4 import BeautifulSoup


class LocalNewsFetcher:
    """
    幡ヶ谷・渋谷区周辺のローカル情報を取得するクラス。
    完全自動実行前提。取得に失敗してもダミー情報を返し、止まらない。
    """

    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    def fetch_shibuya_city_news(self) -> list[str]:
        """
        渋谷区の公式サイト等からイベントっぽいタイトルを拾う例。
        実際の構造変化に対してはベストエフォートで動く想定。
        """
        urls = [
            "https://www.city.shibuya.tokyo.jp/",
        ]
        titles: list[str] = []

        for url in urls:
            try:
                resp = requests.get(url, timeout=self.timeout)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                for h in soup.find_all(["h1", "h2", "h3", "a"]):
                    text = (h.get_text() or "").strip()
                    if not text:
                        continue
                    if any(key in text for key in ["イベント", "祭", "まつり", "フェス", "観光"]):
                        titles.append(text)
            except Exception as e:
                print(f"[LocalNewsFetcher] shibuya city fetch error: {e}")

        return titles

    def fetch_hatagaya_topics(self) -> list[str]:
        """
        幡ヶ谷というキーワードを含むページからタイトルを拾う例。
        実際には商店街サイトやポータルなどに差し替え可能だが、
        人手前提にはせず、URLが空でも問題なく動作する。
        """
        urls: list[str] = []
        titles: list[str] = []

        for url in urls:
            try:
                resp = requests.get(url, timeout=self.timeout)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                for h in soup.find_all(["h1", "h2", "h3", "a"]):
                    text = (h.get_text() or "").strip()
                    if not text:
                        continue
                    if "幡ヶ谷" in text:
                        titles.append(text)
            except Exception as e:
                print(f"[LocalNewsFetcher] hatagaya fetch error: {e}")

        return titles

    def build_local_news_context(self) -> str:
        """
        LLMに渡すためのコンテキスト文字列に整形。
        何も取れなかった場合は、それを踏まえたダミー文章を返す。
        """
        today = datetime.date.today().strftime("%Y-%m-%d")
        news_items: list[str] = []

        news_items.extend(self.fetch_shibuya_city_news())
        news_items.extend(self.fetch_hatagaya_topics())

        if not news_items:
            return dedent(f"""
            日付: {today}
            現時点で自動取得されたローカルニュースは取得できませんでした。

            ただし幡ヶ谷・渋谷区周辺では、
            日々小さなイベントや店舗の変化があります。
            その前提で、
            - 幡ヶ谷の街の雰囲気
            - 幡ヶ谷周辺のグルメやカフェ
            - 幡ヶ谷からのアクセス
            - 季節ごとの過ごし方
            - 商店街や地域イベントの可能性

            などを、旅行者・民泊ゲストの目線で想像しながら
            集客に役立つテーマを考えてください。
            """).strip()

        lines = [f"日付: {today}", "自動取得されたローカルニュース候補:"]
        for t in news_items[:30]:
            lines.append(f"- {t}")

        return "\n".join(lines)
EOF

echo "[INFO] Writing bot/past_titles_db.py ..."
cat > bot/past_titles_db.py <<'EOF'
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from difflib import SequenceMatcher
from typing import List, Tuple

DB_PATH = os.environ.get("PAST_TITLES_DB_PATH", "past_titles.sqlite3")
SIMILARITY_THRESHOLD = float(os.environ.get("TITLE_SIMILARITY_THRESHOLD", "0.85"))
MAX_PAST_TITLES = int(os.environ.get("MAX_PAST_TITLES", "2000"))


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS titles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def add_title(title: str):
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO titles (title, created_at) VALUES (?, ?)",
            (title, now),
        )
        conn.commit()


def fetch_recent_titles(limit: int = MAX_PAST_TITLES) -> List[Tuple[int, str]]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, title FROM titles ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return cur.fetchall()


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def find_similar_titles(candidate: str, threshold: float = SIMILARITY_THRESHOLD) -> List[str]:
    """
    候補タイトルが過去のタイトルとどの程度似ているかチェック。
    threshold 以上のものがあれば、それは「ほぼ同じ内容」とみなす。
    完全自動運用を前提にしつつ、重複を極力避ける。
    """
    similar: List[str] = []
    for _, past_title in fetch_recent_titles():
        if similarity(candidate, past_title) >= threshold:
            similar.append(past_title)
    return similar
EOF

echo "[INFO] Writing bot/main.py ..."
cat > bot/main.py <<'EOF'
import os
import time
from typing import Optional

import requests

from templates import get_static_templates_text
from local_news import LocalNewsFetcher
from past_titles_db import (
    init_db,
    add_title,
    find_similar_titles,
    fetch_recent_titles,
)

# ==== 環境変数 ====

WP_BASE_URL = os.environ.get("WP_URL")
WP_USER = os.environ.get("WP_USER")
WP_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD")

LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://llama:8080")
MODEL_FILE = os.environ.get("MODEL_FILE", "/models/model.gguf")

TOPIC = os.environ.get("TOPIC", "").strip()  # 手動固定テーマ（ふだんは空を想定）

WP_POST_STATUS = os.environ.get("WP_POST_STATUS", "draft")  # publish にすれば即公開

if not WP_BASE_URL:
    raise RuntimeError("WP_URL is not set in environment")

WP_POSTS_URL = WP_BASE_URL.rstrip("/") + "/wp-json/wp/v2/posts"
LLM_COMPLETIONS_URL = LLM_BASE_URL.rstrip("/") + "/v1/completions"


# ==== LLM呼び出し ====

def call_llm(
    prompt: str,
    max_tokens: int = 1024,
    temperature: float = 0.7,
    stop=None,
) -> str:
    """
    llama.cpp (/v1/completions) を叩く汎用関数。
    """
    if stop is None:
        stop = ["</s>"]

    payload = {
        "model": MODEL_FILE,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stop": stop,
    }

    last_error: Optional[Exception] = None
    for i in range(3):
        try:
            resp = requests.post(
                LLM_COMPLETIONS_URL,
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()

            if "choices" in data and data["choices"]:
                text = data["choices"][0].get("text", "")
            else:
                text = data.get("text", "")

            return text.strip()
        except Exception as e:
            last_error = e
            print(f"[call_llm] error ({i+1}/3): {e}")
            time.sleep(2)

    raise RuntimeError(f"LLM request failed after retries: {last_error}")


# ==== テーマ生成エージェント ====

def generate_theme(
    local_news_context: str,
    static_templates_text: str,
) -> str:
    """
    幡ヶ谷 × 民泊 × 集客 に特化したテーマを1つ自動で生成する。
    過去タイトルと類似している場合は複数回リトライする。
    """

    recent = fetch_recent_titles()
    past_titles_text = "\n".join(f"- {title}" for _, title in recent)

    base_prompt = f"""
あなたは「渋谷区・幡ヶ谷エリア」専門の民泊集客コンサルタント兼
ローカルメディア編集長です。

目的：
- 幡ヶ谷エリアの民泊に泊まりに来るお客様を集客するための
  ブログ記事テーマ（タイトル）を1つだけ考えること

条件：
- 毎日1本ずつ、数年にわたり投稿し続ける想定
- 同じ内容・似た内容にならないこと（少なくとも1万通り以上を意識）
- 必ず「幡ヶ谷」または「渋谷区」を含める
- 民泊・宿泊に関係する内容にする（「民泊」か「宿泊」などが文脈に含まれる）
- 抽象的な「〜とは？」だけのタイトルは禁止
- 旅行者や民泊ゲストが検索しそうなキーワードを含める
- 不安解消・具体的なイメージ・街の魅力・アクセス・グルメなど、
  予約や問い合わせにつながる角度を必ず入れる
- 34〜42文字程度で日本語タイトルを1つだけ出力する
- 箇条書き・番号・コメントは禁止。タイトル文字列1行のみ。

今日のローカル情報（自動取得したもの）：
{local_news_context}

幡ヶ谷 × 民泊のテーマの型（自動生成された多数のパターンの一例）：
{static_templates_text}

過去に投稿済みのタイトル一覧（一部）：
{past_titles_text}

上記をすべて踏まえ、まだ扱っていない新しい視点・組み合わせで
幡ヶ谷エリアの民泊集客に役立つブログ記事タイトルを
1つだけ提案してください。
    """.strip()

    last_candidate = None

    for attempt in range(5):
        if attempt == 0:
            prompt = base_prompt
        else:
            prompt = base_prompt + f"""

前回の候補タイトル：
- {last_candidate}

これは既存のタイトルと似ている、または内容が近すぎると判断されたため、
これとは異なる全く新しい切り口のタイトルを
1つだけ再提案してください。
            """.strip()

        raw = call_llm(prompt, max_tokens=128, temperature=0.7)
        first_line = raw.splitlines()[0].strip()

        # 先頭の番号や記号を削る
        candidate = first_line.lstrip("0123456789. 　-・「」『』[]【】")

        # 幡ヶ谷 / 渋谷区 / 民泊or宿泊 が抜けていたときの最低限の自動補正
        if "幡ヶ谷" not in candidate and "渋谷区" not in candidate:
            candidate = f"幡ヶ谷で楽しむ {candidate}"
        if "民泊" not in candidate and "宿泊" not in candidate:
            candidate = candidate + " 民泊宿泊ガイド"

        similar = find_similar_titles(candidate)
        if not similar:
            return candidate

        print(f"[THEME] similar detected (attempt {attempt+1}): {candidate}")
        print(f"[THEME] similar to: {similar[:3]}")
        last_candidate = candidate

    # 5回試しても類似してしまう場合は最後の案を採用（完全自動運用前提）
    return last_candidate or "幡ヶ谷民泊の集客ブログタイトル自動生成"


# ==== 記事本文エージェント ====

def generate_article(theme: str) -> tuple[str, str]:
    """
    テーマ（タイトル）から本文を生成する。
    """
    prompt = f"""
あなたは民泊運営と旅行者ニーズに精通した日本語ライターです。

次のテーマで、渋谷区幡ヶ谷エリアの民泊に泊まりたい人向けに
ブログ記事の本文を書いてください。

テーマ:「{theme}」

▼読者像
- 東京旅行を検討している国内外の旅行者
- 渋谷や新宿に行きたいが、どこに泊まるか悩んでいる人
- 幡ヶ谷のことをあまり知らない人

▼執筆条件
- です・ます調で、親しみやすく丁寧な文体
- 構成は「導入 → 見出し付きの本文（3〜4セクション）→ まとめ」
- 見出しには Markdown 形式で「## 見出しタイトル」を使う
- 文字数はおよそ 1200〜1600 文字
- 幡ヶ谷エリアの魅力・アクセス・周辺の飲食店や観光などを
  できるだけ具体的にイメージしやすく書く
- 不安解消（治安・移動・買い物・言葉の問題など）につながる情報を含める
- 特定の物件名や広告的な表現は避け、一般的な民泊を想定して書く

▼出力形式
- 出力は本文のみ（タイトル行は書かない）
- コードブロックや余計な説明文は付けない
    """.strip()

    body = call_llm(prompt, max_tokens=1500, temperature=0.8)
    return theme, body


# ==== WordPress 投稿 ====

def post_to_wordpress(title: str, content: str, status: str = "draft"):
    data = {
        "title": title,
        "content": content,
        "status": status,
    }
    print(f"[WP] Posting: title={title!r}, status={status}")
    resp = requests.post(
        WP_POSTS_URL,
        json=data,
        auth=(WP_USER, WP_APP_PASSWORD),
        timeout=120,
    )
    if not resp.ok:
        print("[WP] Error:", resp.status_code, resp.text)
        resp.raise_for_status()
    else:
        try:
            link = resp.json().get("link")
        except Exception:
            link = None
        print("[WP] Success:", resp.status_code, link)


# ==== 1回分のフロー ====

def run_once():
    """
    1回の実行で：
    - DB初期化
    - テーマ生成
    - 本文生成
    - WP投稿
    - タイトルをDBに保存
    までを自動で行う。
    """
    init_db()

    # 1. テーマ決定
    if TOPIC:
        theme = TOPIC
        print(f"[THEME] Using fixed TOPIC from .env: {theme}")
    else:
        fetcher = LocalNewsFetcher()
        local_news_context = fetcher.build_local_news_context()
        static_templates_text = get_static_templates_text()
        theme = generate_theme(local_news_context, static_templates_text)
        print(f"[THEME] Generated theme: {theme}")

    # 2. 本文生成
    title, content = generate_article(theme)
    print(f"[ARTICLE] Generated article length: {len(content)} characters")

    # 3. WordPress に投稿
    post_to_wordpress(title, content, status=WP_POST_STATUS)

    # 4. タイトルをDBに保存
    add_title(title)
    print("[DB] Title stored")


def main():
    run_once()


if __name__ == "__main__":
    main()
EOF

echo "[INFO] Writing bot/scheduler.py ..."
cat > bot/scheduler.py <<'EOF'
import os
import time
import traceback
from datetime import datetime, timedelta

from main import run_once

INTERVAL_HOURS = float(os.environ.get("SCHEDULER_INTERVAL_HOURS", "24"))


def main():
    """
    コンテナ起動後：
    - すぐに1回 run_once()
    - その後 INTERVAL_HOURS ごとに永久ループ
    """
    while True:
        now = datetime.now()
        print(f"[SCHEDULER] Start job at {now.isoformat()}")
        try:
            run_once()
        except Exception as e:
            print("[SCHEDULER] Error during job:", e)
            traceback.print_exc()

        sleep_seconds = int(INTERVAL_HOURS * 3600)
        next_time = now + timedelta(seconds=sleep_seconds)
        print(f"[SCHEDULER] Next job scheduled at {next_time.isoformat()}")
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    main()
EOF

# ---------------------------------------------------------
# 3. docker-compose.yml をバックアップしてから差し替え
# ---------------------------------------------------------
if [ -f docker-compose.yml ]; then
  backup="docker-compose.yml.bak.$(date +%Y%m%d%H%M%S)"
  echo "[INFO] Backing up existing docker-compose.yml to $backup"
  cp docker-compose.yml "$backup"
fi

echo "[INFO] Writing new docker-compose.yml ..."
cat > docker-compose.yml <<'EOF'
version: "3.9"

services:
  llama:
    image: ghcr.io/ggerganov/llama.cpp:full
    container_name: llama-server
    command: >
      --server
      -m ${MODEL_FILE}
      -c 1024
      -n 256
      --host 0.0.0.0
      --port 8080
    volumes:
      - ./models:/models
    ports:
      - "8080:8080"
    env_file:
      - .env

  bot:
    build: ./bot
    env_file:
      - .env
    depends_on:
      - llama
    # 手動で1回だけ動かしたいとき用:
    #   docker-compose run --rm bot
    command: ["python", "main.py"]

  scheduler:
    build: ./bot
    env_file:
      - .env
    depends_on:
      - llama
    command: ["python", "scheduler.py"]
    restart: unless-stopped
EOF

echo "[INFO] All done."
echo "[INFO] Backup: $BACKUP_TAR"
echo
echo "次のコマンドでビルド＆起動できます:"
echo "  docker-compose build bot"
echo "  docker-compose down"
echo "  docker-compose up -d llama scheduler"
echo
echo "手動テスト用:"
echo "  docker-compose run --rm bot"

