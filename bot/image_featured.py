import io
import os
import random
from typing import Optional, Tuple

import requests
from PIL import Image, ImageDraw, ImageFont

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account

# ====== 環境変数 ======
WP_BASE_URL = os.environ.get("WP_URL")
WP_USER = os.environ.get("WP_USER")
WP_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD")

GDRIVE_FOLDER_ID = os.environ.get("GDRIVE_FOLDER_ID")  # 親フォルダID
GOOGLE_CREDS_PATH = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")  # サービスアカウントJSON

FONT_PATH = os.environ.get("FONT_PATH", "")  # 任意。日本語フォントを指定すると綺麗に出る
IMAGE_SIZE = (1080, 1080)  # Instagram向け正方形

if not (WP_BASE_URL and WP_USER and WP_APP_PASSWORD):
    raise RuntimeError("WP_URL / WP_USER / WP_APP_PASSWORD are required")

if not (GDRIVE_FOLDER_ID and GOOGLE_CREDS_PATH):
    raise RuntimeError("GDRIVE_FOLDER_ID / GOOGLE_APPLICATION_CREDENTIALS are required")


# ====== Google Drive 周り ======

def _build_drive_service():
    creds = service_account.Credentials.from_service_account_file(
        GOOGLE_CREDS_PATH,
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    service = build("drive", "v3", credentials=creds, cache_discovery=False)
    return service


def _walk_drive_images(service, root_folder_id: str):
    """
    root_folder_id 以下を再帰的に辿って画像ファイルを列挙する。
    戻り値: [(file_id, file_name), ...]
    """
    results = []
    queue = [root_folder_id]

    while queue:
        folder_id = queue.pop(0)
        page_token = None
        while True:
            resp = service.files().list(
                q=f"'{folder_id}' in parents and trashed = false",
                fields="nextPageToken, files(id, name, mimeType)",
                pageToken=page_token,
            ).execute()

            for f in resp.get("files", []):
                mime = f.get("mimeType", "")
                if mime == "application/vnd.google-apps.folder":
                    # サブフォルダ → キューに追加
                    queue.append(f["id"])
                elif mime.startswith("image/"):
                    results.append((f["id"], f["name"]))

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    return results


def pick_random_image_from_drive() -> Tuple[str, str]:
    """
    親フォルダ以下からランダムに1枚画像を選ぶ。
    戻り値: (file_id, file_name)
    """
    service = _build_drive_service()
    images = _walk_drive_images(service, GDRIVE_FOLDER_ID)
    if not images:
        raise RuntimeError("No images found under the Google Drive folder.")
    file_id, file_name = random.choice(images)
    print(f"[DRIVE] picked image: {file_name} ({file_id})")
    return file_id, file_name


def download_image_from_drive(file_id: str) -> Image.Image:
    service = _build_drive_service()
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
        # print(f"[DRIVE] Download {int(status.progress() * 100)}%")
    fh.seek(0)
    img = Image.open(fh).convert("RGB")
    return img


# ====== 画像加工（正方形＋文字入れ） ======

def _resize_to_square(img: Image.Image, size=(1080, 1080)) -> Image.Image:
    # アスペクト比を保ちつつ最短辺に合わせて拡大→中央クロップ
    w, h = img.size
    target_w, target_h = size

    scale = max(target_w / w, target_h / h)
    new_w = int(w * scale)
    new_h = int(h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    right = left + target_w
    bottom = top + target_h
    img = img.crop((left, top, right, bottom))
    return img


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    if FONT_PATH and os.path.exists(FONT_PATH):
        return ImageFont.truetype(FONT_PATH, size=size)
    return ImageFont.load_default()


def _wrap_ja(text: str, max_chars: int) -> str:
    lines = []
    line = ""
    for ch in text:
        line += ch
        if len(line) >= max_chars:
            lines.append(line)
            line = ""
    if line:
        lines.append(line)
    return "\n".join(lines)


def add_text_overlay(
    img: Image.Image,
    main_text: str,
    sub_text: Optional[str] = None,
) -> Image.Image:
    img = img.copy()
    img = _resize_to_square(img, IMAGE_SIZE)
    w, h = img.size

    img_rgba = img.convert("RGBA")
    overlay_h = int(h * 0.26)
    overlay = Image.new("RGBA", (w, overlay_h), (0, 0, 0, 150))
    img_rgba.paste(overlay, (0, h - overlay_h), overlay)

    draw = ImageDraw.Draw(img_rgba)

    font_main = _get_font(60)
    font_sub = _get_font(36)

    main_text_wrapped = _wrap_ja(main_text[:30], max_chars=12)
    sub_text_wrapped = _wrap_ja(sub_text[:50], max_chars=18) if sub_text else ""

    margin = 40
    y = h - overlay_h + margin

    draw.multiline_text(
        (margin, y),
        main_text_wrapped,
        font=font_main,
        fill=(255, 255, 255, 255),
        spacing=8,
    )

    if sub_text_wrapped:
        _, _, _, main_h = draw.multiline_textbbox(
            (margin, y),
            main_text_wrapped,
            font=font_main,
            spacing=8,
        )
        y_sub = y + main_h + 20
        draw.multiline_text(
            (margin, y_sub),
            sub_text_wrapped,
            font=font_sub,
            fill=(230, 230, 230, 255),
            spacing=6,
        )

    return img_rgba.convert("RGB")


# ====== WordPress に画像アップロード & アイキャッチ設定 ======

def upload_image_to_wordpress(img: Image.Image, filename: str) -> Tuple[int, str]:
    """
    画像をWPにアップロードし、(メディアID, 画像URL) を返す。
    """
    media_url = WP_BASE_URL.rstrip("/") + "/wp-json/wp/v2/media"

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    buf.seek(0)

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": "image/jpeg",
    }

    resp = requests.post(
        media_url,
        headers=headers,
        data=buf.getvalue(),
        auth=(WP_USER, WP_APP_PASSWORD),
    )
    if not resp.ok:
        print("[WP-MEDIA] Error:", resp.status_code, resp.text)
        resp.raise_for_status()

    data = resp.json()
    media_id = data.get("id")
    image_url = data.get("source_url")
    print(f"[WP-MEDIA] Uploaded image id={media_id}, url={image_url}")
    return media_id, image_url


def set_post_featured_media(post_id: int, media_id: int):
    post_url = WP_BASE_URL.rstrip("/") + f"/wp-json/wp/v2/posts/{post_id}"
    payload = {"featured_media": media_id}
    resp = requests.post(
        post_url,
        json=payload,
        auth=(WP_USER, WP_APP_PASSWORD),
    )
    if not resp.ok:
        print("[WP-POST] Error setting featured_media:", resp.status_code, resp.text)
        resp.raise_for_status()
    print(f"[WP-POST] featured_media set. post_id={post_id}, media_id={media_id}")


# ====== 外から呼ぶメイン関数 ======

def attach_featured_image_from_drive(
    post_id: int,
    post_title: str,
    post_link: Optional[str] = None,
) -> Optional[str]:
    """
    - Google Drive からランダムに1枚画像を取得
    - 正方形＋文字入れ
    - WordPressにアップロード
    - 対象記事に featured_media として設定
    - 最後に「アップロードされた画像URL」を返す（Instagram用）
    """
    if not post_id:
        print("[FEATURED] no post_id, skip.")
        return None

    file_id, file_name = pick_random_image_from_drive()
    img = download_image_from_drive(file_id)

    # 画像上のテキストは「タイトル＋URL（あれば）」くらいにしておく
    sub = post_link if post_link else None
    img_processed = add_text_overlay(img, main_text=post_title, sub_text=sub)

    # WordPressへアップロード
    safe_filename = f"featured_{post_id}.jpg"
    media_id, image_url = upload_image_to_wordpress(img_processed, safe_filename)

    # アイキャッチに設定
    set_post_featured_media(post_id, media_id)

    # Instagram 用に画像URLを返す
    return image_url

