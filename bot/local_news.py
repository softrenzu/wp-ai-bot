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
                resp = requests.get(
                    url,
                    timeout=self.timeout,
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                for h in soup.find_all(["h1", "h2", "h3", "a"]):
                    text = (h.get_text() or "").strip()
                    if not text or len(text) < 8:
                        continue
                    if any(k in text for k in ["イベント", "祭", "まつり", "フェス", "観光", "開催"]):
                        titles.append(text)
            except Exception as e:
                print(f"[LocalNewsFetcher] shibuya fetch error: {e}")
        return titles

    def fetch_hatagaya_topics(self) -> list[str]:
        """
        幡ヶ谷・笹塚・幡ヶ谷商店街のローカル情報を取得する。
        """
        urls = [
            "https://www.hatagaya.com/",            # 幡ヶ谷商店街
            "https://sasakacho.jp/",                 # 笹塚商店街（隣駅・関連エリア）
        ]
        titles: list[str] = []
        for url in urls:
            try:
                resp = requests.get(
                    url,
                    timeout=self.timeout,
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                for h in soup.find_all(["h1", "h2", "h3", "a"]):
                    text = (h.get_text() or "").strip()
                    if not text or len(text) < 8:
                        continue
                    if any(k in text for k in [
                        "幡ヶ谷", "笹塚", "イベント", "セール", "祭", "フェア",
                        "オープン", "グルメ", "カフェ", "新店",
                    ]):
                        titles.append(text)
            except Exception as e:
                print(f"[LocalNewsFetcher] hatagaya fetch error: {e}")
        return titles

    def fetch_google_news_rss(self) -> list[str]:
        """
        Google News RSSで「幡ヶ谷」「渋谷区 イベント」を取得する。
        """
        queries = ["幡ヶ谷", "渋谷区+イベント"]
        titles: list[str] = []
        for q in queries:
            url = f"https://news.google.com/rss/search?q={q}&hl=ja&gl=JP&ceid=JP:ja"
            try:
                resp = requests.get(url, timeout=self.timeout)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "xml")
                for item in soup.find_all("item")[:5]:
                    title_tag = item.find("title")
                    if title_tag:
                        titles.append(title_tag.get_text().strip())
            except Exception as e:
                print(f"[LocalNewsFetcher] google news fetch error ({q}): {e}")
        return titles

    def build_local_news_context(self) -> str:
        today = datetime.date.today().strftime("%Y-%m-%d")
        news_items: list[str] = []
        news_items.extend(self.fetch_shibuya_city_news())
        news_items.extend(self.fetch_hatagaya_topics())
        news_items.extend(self.fetch_google_news_rss())

        # 重複排除
        seen = set()
        unique_items = []
        for item in news_items:
            if item not in seen:
                seen.add(item)
                unique_items.append(item)

        if not unique_items:
            # ★ フォールバック：AIに「想像して」と言わない。泉庵固有のテーマを渡す
            return dedent(f"""
                日付: {today}
                ローカルニュースの自動取得はできませんでした。

                代わりに以下の泉庵固有テーマから記事を作成してください：
                - 幡ヶ谷商店街の散歩と泉庵滞在の組み合わせ
                - ねじしき（鶏ガララーメン）とGato（カフェ）の紹介
                - 泉庵から下北沢への行き方と楽しみ方
                - 新宿・渋谷30分圏内の拠点としての泉庵
                - 古民家の布団・畳で眠る体験（実際のゲスト談）
                - 幡ヶ谷の静かな住宅街に泊まる理由
                - 1日1組限定・完全貸切という安心感

                ※これらはすべて実際のゲストレビューに基づいたリアルな体験です。
            """).strip()

        lines = [f"日付: {today}", "取得されたローカルニュース・トピック:"]
        for t in unique_items[:20]:
            lines.append(f"- {t}")
        lines.append("")
        lines.append("※上記の実際のトピックを参考にしつつ、泉庵 Izumianの文脈で記事テーマを考えてください。")
        return "\n".join(lines)

