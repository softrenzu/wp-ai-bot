import os
import sys
import time
import requests
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN")
IG_BUSINESS_ID = os.environ.get("IG_BUSINESS_ID")

if not ACCESS_TOKEN or not IG_BUSINESS_ID:
    print("[ERROR] IG_ACCESS_TOKEN または IG_BUSINESS_ID が環境変数にありません")
    sys.exit(1)

GRAPH_API = "https://graph.facebook.com/v24.0"

def wait_until_ready(creation_id, timeout=120, interval=10):
    """Instagram メディアが publish 可能になるまで待つ"""
    status_url = f"{GRAPH_API}/{creation_id}"
    waited = 0

    while waited < timeout:
        res = requests.get(
            status_url,
            params={
                "fields": "status_code",
                "access_token": ACCESS_TOKEN,
            },
        )
        res.raise_for_status()
        status = res.json().get("status_code")
        print(f"[IG] status_check: {status}")

        if status == "FINISHED":
            return True

        time.sleep(interval)
        waited += interval

    return False


def post_to_instagram(image_url: str, caption: str):
    # 1) メディアオブジェクト作成
    create_url = f"{GRAPH_API}/{IG_BUSINESS_ID}/media"
    create_res = requests.post(
        create_url,
        data={
            "image_url": image_url,
            "caption": caption,
            "access_token": ACCESS_TOKEN,
        },
    )
    print("[IG] create_res:", create_res.status_code, create_res.text)
    create_res.raise_for_status()

    creation_id = create_res.json()["id"]

    # 2) メディア準備完了待ち（超重要）
    if not wait_until_ready(creation_id):
        raise RuntimeError("Instagram media was not ready in time")

    # 3) 公開
    publish_url = f"{GRAPH_API}/{IG_BUSINESS_ID}/media_publish"
    publish_res = requests.post(
        publish_url,
        data={
            "creation_id": creation_id,
            "access_token": ACCESS_TOKEN,
        },
    )
    print("[IG] publish_res:", publish_res.status_code, publish_res.text)
    publish_res.raise_for_status()

    return publish_res.json()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("使い方: python instagram_post.py IMAGE_URL CAPTION")
        sys.exit(1)

    image_url = sys.argv[1]
    caption = sys.argv[2]

    res = post_to_instagram(image_url, caption)
    print("[IG] 投稿完了:", res)
