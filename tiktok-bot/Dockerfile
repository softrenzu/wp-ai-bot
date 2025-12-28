FROM python:3.10-slim

RUN apt-get update && apt-get install -y ffmpeg && apt-get clean

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY post_tiktok.py .
COPY last_tiktok_post.json .

CMD ["python", "post_tiktok.py"]
