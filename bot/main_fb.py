import os
import requests
from facebook_post import post_to_facebook

# ★ bash source を使わず .env を Python で読む
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

WP_BASE_URL = os.environ.get("WP_URL")
WP_USER = os.environ.get("WP_USER")
WP_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD")

if not (WP_BASE_URL and WP_USER and WP_APP_PASSWORD):
    raise RuntimeError("WP_URL / WP_USER / WP_APP_PASSWORD が必要です")

POSTS_API = WP_BASE_URL.rstrip("/") + "/wp-json/wp/v2/posts"

def fetch_latest_post():
    resp = requests.get(
        POSTS_API,
        params={
            "per_page": 1,
            "orderby": "date",
            "order": "desc",
            "_embed": "1",
            "status": "publish",
        },
        auth=(WP_USER, WP_APP_PASSWORD),
        timeout=15,
    )
    resp.raise_for_status()
    post = resp.json()[0]

    title = post["title"]["rendered"]
    link = post["link"]

    media = post.get("_embedded", {}).get("wp:featuredmedia", [])
    if not media:
        raise RuntimeError("アイキャッチ画像がありません")

    image_url = media[0]["source_url"]
    return title, link, image_url

if __name__ == "__main__":
    title, link, image_url = fetch_latest_post()

    caption = f"""{title}

{link}

#民泊 #幡ヶ谷 #渋谷区 #staytokyo
"""

    post_to_facebook(image_url, caption)
