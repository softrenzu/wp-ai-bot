import os
import requests

FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
FB_PAGE_ACCESS_TOKEN = os.environ.get("FB_PAGE_ACCESS_TOKEN")

if not FB_PAGE_ID or not FB_PAGE_ACCESS_TOKEN:
    raise RuntimeError("FB_PAGE_ID / FB_PAGE_ACCESS_TOKEN が必要です")

GRAPH_API = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/photos"

def post_to_facebook(image_url: str, caption: str):
    payload = {
        "url": image_url,
        "caption": caption,
        "access_token": FB_PAGE_ACCESS_TOKEN,
    }

    resp = requests.post(GRAPH_API, data=payload, timeout=20)
    resp.raise_for_status()
    return resp.json()
