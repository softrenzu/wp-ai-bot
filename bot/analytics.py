import json
import os
from datetime import date, timedelta
from typing import Any, Dict, List

from google.oauth2 import service_account
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
CREDENTIALS_FILE = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "/secrets/wordpress-gdrive.json")
SITE_URL = os.environ.get("SEARCH_CONSOLE_SITE_URL", "https://staytokyo.xyz/")
DAYS = int(os.environ.get("SEARCH_CONSOLE_DAYS", "28"))


def get_service():
    credentials = service_account.Credentials.from_service_account_file(
        CREDENTIALS_FILE,
        scopes=SCOPES,
    )
    return build("searchconsole", "v1", credentials=credentials)


def list_sites() -> Dict[str, Any]:
    service = get_service()
    return service.sites().list().execute()


def fetch_page_performance(row_limit: int = 100) -> List[Dict[str, Any]]:
    service = get_service()

    # Search Consoleは直近1〜2日が未確定のことがあるため2日前までを見る
    end_date = date.today() - timedelta(days=2)
    start_date = end_date - timedelta(days=DAYS)

    body = {
        "startDate": start_date.isoformat(),
        "endDate": end_date.isoformat(),
        "dimensions": ["page"],
        "rowLimit": row_limit,
        "startRow": 0,
    }

    response = service.searchanalytics().query(
        siteUrl=SITE_URL,
        body=body,
    ).execute()

    rows = response.get("rows", [])
    pages = []

    for row in rows:
        page = row.get("keys", [""])[0]
        clicks = row.get("clicks", 0)
        impressions = row.get("impressions", 0)
        ctr = row.get("ctr", 0)
        position = row.get("position", 0)

        pages.append({
            "page": page,
            "clicks": clicks,
            "impressions": impressions,
            "ctr": ctr,
            "position": position,
        })

    pages.sort(key=lambda x: (x["clicks"], x["impressions"]), reverse=True)
    return pages


def fetch_query_performance(row_limit: int = 100) -> List[Dict[str, Any]]:
    service = get_service()

    end_date = date.today() - timedelta(days=2)
    start_date = end_date - timedelta(days=DAYS)

    body = {
        "startDate": start_date.isoformat(),
        "endDate": end_date.isoformat(),
        "dimensions": ["query", "page"],
        "rowLimit": row_limit,
        "startRow": 0,
    }

    response = service.searchanalytics().query(
        siteUrl=SITE_URL,
        body=body,
    ).execute()

    rows = response.get("rows", [])
    items = []

    for row in rows:
        keys = row.get("keys", ["", ""])
        query = keys[0] if len(keys) > 0 else ""
        page = keys[1] if len(keys) > 1 else ""

        items.append({
            "query": query,
            "page": page,
            "clicks": row.get("clicks", 0),
            "impressions": row.get("impressions", 0),
            "ctr": row.get("ctr", 0),
            "position": row.get("position", 0),
        })

    items.sort(key=lambda x: (x["clicks"], x["impressions"]), reverse=True)
    return items


def main():
    print(f"[INFO] SITE_URL={SITE_URL}")
    print(f"[INFO] DAYS={DAYS}")

    pages = fetch_page_performance()
    queries = fetch_query_performance()

    result = {
        "site_url": SITE_URL,
        "days": DAYS,
        "top_pages": pages[:30],
        "top_queries": queries[:30],
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
