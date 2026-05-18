import os
import sys
import json
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv("/home/ubuntu/wp-ai-bot/.env")

BASE_DIR = Path("/home/ubuntu/wp-ai-bot")
BOT_DIR = BASE_DIR / "bot"
OUTPUT_DIR = BASE_DIR / "output"
LOG_DIR = BASE_DIR / "logs"

THREADS_ACCESS_TOKEN = os.getenv("THREADS_ACCESS_TOKEN", "").strip()
THREADS_USER_ID = os.getenv("THREADS_USER_ID", "").strip()
THREADS_API_BASE = os.getenv("THREADS_API_BASE", "https://graph.threads.net/v1.0").strip()

# 既存Instagram運用と同じテーマ/生成を使うための候補
# あなたの過去構成に合わせて「既存の投稿生成結果」を優先的に拾う
CANDIDATE_TEXT_FILES = [
    OUTPUT_DIR / "instagram_caption.txt",
    OUTPUT_DIR / "caption.txt",
    OUTPUT_DIR / "post.txt",
    OUTPUT_DIR / "latest_caption.txt",
    OUTPUT_DIR / "meta.json",
]

def fail(msg: str):
    print(f"[ERROR] {msg}", file=sys.stderr)
    sys.exit(1)

def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.strip()

def load_text_from_existing_outputs() -> str:
    for path in CANDIDATE_TEXT_FILES:
        if not path.exists():
            continue

        if path.name.endswith(".json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                for key in ["caption", "post_text", "text", "description", "title"]:
                    val = data.get(key)
                    if isinstance(val, str) and val.strip():
                        return normalize_text(val)
            except Exception:
                pass
        else:
            try:
                txt = path.read_text(encoding="utf-8").strip()
                if txt:
                    return normalize_text(txt)
            except Exception:
                pass

    return ""

def load_text_from_generator() -> str:
    """
    既存Instagramの本文生成を極力再利用する。
    bot/main.py が持つ generate_article 等を優先的に探す。
    """
    sys.path.insert(0, str(BOT_DIR))
    # 1) llm_client.generate_article
    try:
        from llm_client import generate_article  # type: ignore
        theme = os.getenv("THREADS_THEME") or os.getenv("POST_THEME") or os.getenv("TOPIC") or "泉庵東京の宿泊体験"
        text = generate_article(theme)
        if isinstance(text, str) and text.strip():
            return normalize_text(text)
    except Exception:
        pass

    # 2) main.py から関数候補を探す
    try:
        import main as ig_main  # type: ignore

        for fn_name in [
            "generate_article",
            "generate_caption",
            "build_caption",
            "create_caption",
            "make_caption",
            "generate_post_text",
        ]:
            fn = getattr(ig_main, fn_name, None)
            if callable(fn):
                try:
                    text = fn()
                    if isinstance(text, str) and text.strip():
                        return normalize_text(text)
                except TypeError:
                    theme = os.getenv("THREADS_THEME") or os.getenv("POST_THEME") or os.getenv("TOPIC") or "泉庵東京の宿泊体験"
                    try:
                        text = fn(theme)
                        if isinstance(text, str) and text.strip():
                            return normalize_text(text)
                    except Exception:
                        pass
                except Exception:
                    pass
    except Exception:
        pass

    return ""

def apply_threads_style(text: str) -> str:
    """
    Instagramと同じ内容を基本にしつつ、Threads向けに長すぎる場合だけ軽く詰める。
    """
    text = normalize_text(text)

    # 投稿末尾にThreads用タグを任意追加
    suffix = os.getenv("THREADS_SUFFIX", "").strip()
    if suffix:
        text = f"{text}\n\n{suffix}"

    # 長すぎる場合のみ切る
    max_chars = int(os.getenv("THREADS_MAX_CHARS", "450"))
    if len(text) > max_chars:
        text = text[:max_chars - 1].rstrip() + "…"
    return text

def create_container(post_text: str) -> str:
    url = f"{THREADS_API_BASE}/{THREADS_USER_ID}/threads"
    data = {
        "media_type": "TEXT",
        "text": post_text,
        "access_token": THREADS_ACCESS_TOKEN,
    }
    r = requests.post(url, data=data, timeout=60)
    if r.status_code >= 400:
        fail(f"create failed: {r.status_code} {r.text}")
    js = r.json()
    creation_id = js.get("id")
    if not creation_id:
        fail(f"creation id missing: {js}")
    print(f"[THREADS] creation_id={creation_id}")
    return creation_id

def publish_container(creation_id: str) -> str:
    url = f"{THREADS_API_BASE}/{THREADS_USER_ID}/threads_publish"
    data = {
        "creation_id": creation_id,
        "access_token": THREADS_ACCESS_TOKEN,
    }
    r = requests.post(url, data=data, timeout=60)
    if r.status_code >= 400:
        fail(f"publish failed: {r.status_code} {r.text}")
    js = r.json()
    post_id = js.get("id")
    if not post_id:
        fail(f"post id missing: {js}")
    print(f"[THREADS] post_id={post_id}")
    return post_id

def main():
    if not THREADS_ACCESS_TOKEN:
        fail("THREADS_ACCESS_TOKEN missing in /home/ubuntu/wp-ai-bot/.env")
    if not THREADS_USER_ID:
        fail("THREADS_USER_ID missing in /home/ubuntu/wp-ai-bot/.env")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # まず既存Instagram生成結果を使う
    post_text = load_text_from_existing_outputs()

    # 見つからなければ既存生成関数を再利用
    if not post_text:
        post_text = load_text_from_generator()

    if not post_text:
        fail("Instagramと同じ投稿本文を取得できませんでした。output配下または既存生成関数を確認してください。")

    post_text = apply_threads_style(post_text)

    print("----- THREADS POST BEGIN -----")
    print(post_text)
    print("----- THREADS POST END -----")

    creation_id = create_container(post_text)
    time.sleep(2)
    post_id = publish_container(creation_id)

    (OUTPUT_DIR / "threads_last_post.txt").write_text(post_text, encoding="utf-8")
    (OUTPUT_DIR / "threads_last_result.json").write_text(
        json.dumps({"creation_id": creation_id, "post_id": post_id}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("[OK] Threads post completed")

if __name__ == "__main__":
    main()
