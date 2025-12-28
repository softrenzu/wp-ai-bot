import os
import requests
import json
from datetime import datetime

API_KEY = "53680081-406fa751273ca30093187a5fd"
BGM_DIR = os.path.join(os.path.dirname(__file__), "bgm")

os.makedirs(BGM_DIR, exist_ok=True)

def download_music():
    print("[INFO] Fetching free BGM from Pixabay...")
    url = f"https://pixabay.com/api/music/?key={API_KEY}&per_page=5&order=latest"

    r = requests.get(url)
    data = r.json()

    if "hits" not in data or len(data["hits"]) == 0:
        print("[ERROR] No tracks returned from Pixabay")
        return

    # 最新の曲を選択（1曲）
    track = data["hits"][0]

    download_url = track["audio"]
    title = track["id"]

    filename = f"{title}.mp3"
    filepath = os.path.join(BGM_DIR, filename)

    print(f"[INFO] Downloading: {filename}")

    audio_data = requests.get(download_url)
    with open(filepath, "wb") as f:
        f.write(audio_data.content)

    print(f"[INFO] Saved to {filepath}")

    cleanup_bgm_folder()

def cleanup_bgm_folder():
    files = [
        os.path.join(BGM_DIR, f)
        for f in os.listdir(BGM_DIR)
        if f.endswith(".mp3")
    ]

    if len(files) <= 2:
        return

    # 古いファイルから削除
    files.sort(key=lambda x: os.path.getctime(x))

    while len(files) > 2:
        old = files.pop(0)
        print(f"[INFO] Removing old BGM: {old}")
        os.remove(old)

if __name__ == "__main__":
    download_music()
