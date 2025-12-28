FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ★ ここを追加（日本語フォント）
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        fontconfig \
        fonts-noto-cjk && \
    rm -rf /var/lib/apt/lists/*

COPY . .

CMD ["python", "main.py"]
