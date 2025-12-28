import datetime
from textwrap import dedent

import requests
from bs4 import BeautifulSoup


class LocalNewsFetcher:
    """
    幡ヶ谷・渋谷区周辺のローカル情報を取得するクラス。
    失敗してもダミー情報を返し、処理を止めない。
    """

    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    def fetch_shibuya_city_news(self) -> list[str]:
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
                    if any(k in text for k in ["イベント", "祭", "まつり", "フェス", "観光"]):
                        titles.append(text)
            except Exception as e:
                print(f"[LocalNewsFetcher] shibuya fetch error: {e}")

        return titles

    def fetch_hatagaya_topics(self) -> list[str]:
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
