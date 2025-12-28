import os
import json
import random
import requests
import subprocess
from openai import OpenAI

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BGM_DIR  = os.path.join(BASE_DIR, "bgm")
LAST_FILE = os.path.join(BASE_DIR, "last_tiktok_post.json")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def analyze_music_preference(title, content):
    prompt = f"""
    Analyze the theme of the following article and suggest the ideal music mood for a TikTok background BGM.

    Title: {title}
    Content: {content}

    Respond in JSON:
    {{
        "genre": "chill / cafe / bright / dark / upbeat / ambient / lofi",
        "mood": "calm / cozy / energetic / happy / sad",
        "energy": 1-10
    }}
    """
    res = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    return json.loads(res.choices[0].message.content)


def score_bgm_tracks(preference):
    files = [
        f for f in os.listdir(BGM_DIR)
        if f.endswith(".mp3")
    ]

    if not files:
        print("[WARN] No BGM tracks available.")
        return None

    scored = []
    for f in files:
        # 現状はランダム + 将来スコアロジック追加しやすい構造
        score = random.uniform(0, 1)
        scored.append((f, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    selected = scored[0][0]

    print(f"[INFO] Selected BGM: {selected}")
    return os.path.join(BGM_DIR, selected)


def get_latest_post():
    url = f"{os.getenv('WP_SITE_URL')}/wp-json/wp/v2/posts?per_page=1"
    res = requests.get(url).json()[0]

    post_id = res["id"]
    title = res["title"]["rendered"]
    content = res["content"]["rendered"]

    media_url = res["_links"]["wp:featuredmedia"][0]["href"]
    media_json = requests.get(media_url).json()
    image_url = media_json["source_url"]

    return post_id, title, content, image_url


def already_posted(post_id):
    if not os.path.exists(LAST_FILE):
        return False

    with open(LAST_FILE, "r") as f:
        data = json.load(f)

    return data.get("last_post_id") == post_id


def save_last_post(post_id):
    with open(LAST_FILE, "w") as f:
        json.dump({"last_post_id": post_id}, f)


def make_voice(text):
    response = client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice="alloy",
        input=text,
    )
    path = os.path.join(BASE_DIR, "voice.mp3")
    with open(path, "wb") as f:
        f.write(response.read())
    return path


def download_image(url):
    path = os.path.join(BASE_DIR, "image.jpg")
    img = requests.get(url)
    with open(path, "wb") as f:
        f.write(img.content)
    return path


def make_video(image, voice, bgm):
    out = os.path.join(BASE_DIR, "output.mp4")

    # 動画内に https://staytokyo.xyz/ を表示（白文字・中央下）
    drawtext = (
        "drawtext=text='https://staytokyo.xyz/':"
        "fontcolor=white:fontsize=40:"
        "x=(w-text_w)/2:y=h-100"
    )

    if bgm:
        filter_complex = (
            "[1:a]volume=1.0[a1];"
            "[2:a]volume=0.3[a2];"
            "[a1][a2]amix=inputs=2:duration=first[aout];"
            f"[0:v]{drawtext}[vout]"
        )

        cmd = [
            "ffmpeg",
            "-loop", "1",
            "-i", image,
            "-i", voice,
            "-i", bgm,
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "[aout]",
            "-c:v", "libx264",
            "-tune", "stillimage",
            "-c:a", "aac",
            "-pix_fmt", "yuv420p",
            "-shortest",
            "-y",
            out
        ]

    else:
        filter_complex = f"[0:v]{drawtext}[vout]"

        cmd = [
            "ffmpeg",
            "-loop", "1",
            "-i", image,
            "-i", voice,
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "1:a",
            "-c:v", "libx264",
            "-tune", "stillimage",
            "-c:a", "aac",
            "-pix_fmt", "yuv420p",
            "-shortest",
            "-y",
            out
        ]

    subprocess.run(cmd, check=True)
    return out


def upload_to_tiktok(video_path, title):
    url = "https://open-api.tiktok.com/v2/video/upload/"

    files = {"video": open(video_path, "rb")}

    # ← ここで caption に URL を必ず追加する
    caption = f"{title}\n詳しくはこちら：https://staytokyo.xyz/"

    data = {
        "access_token": os.getenv("TIKTOK_ACCESS_TOKEN"),
        "caption": caption
    }

    res = requests.post(url, data=data, files=files)
    print("[TikTok] Response:", res.text)
    return res.json()


if __name__ == "__main__":
    post_id, title, content, image_url = get_latest_post()

    if already_posted(post_id):
        print("[TikTok] Already posted. Skip.")
        exit()

    preference = analyze_music_preference(title, content)
    bgm = score_bgm_tracks(preference)

    voice = make_voice(title + "。" + content)
    image = download_image(image_url)
    video = make_video(image, voice, bgm)

    upload_to_tiktok(video, title)
    save_last_post(post_id)

    print("[TikTok] Done:", post_id)
