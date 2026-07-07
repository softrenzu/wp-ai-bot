import json
import os
from datetime import datetime
from typing import Any, Dict, List

from analytics import fetch_page_performance, fetch_query_performance


FEEDBACK_FILE = os.environ.get("PROMPT_FEEDBACK_FILE", "/secrets/prompt_feedback.json")
SITE_URL = os.environ.get("SEARCH_CONSOLE_SITE_URL", "https://staytokyo.xyz/")


def pct(value: float) -> float:
    return round(float(value or 0) * 100, 2)


def compact_pages(pages: List[Dict[str, Any]], limit: int = 20) -> List[Dict[str, Any]]:
    result = []
    for p in pages[:limit]:
        result.append({
            "page": p.get("page"),
            "clicks": p.get("clicks", 0),
            "impressions": p.get("impressions", 0),
            "ctr_percent": pct(p.get("ctr", 0)),
            "position": round(float(p.get("position", 0)), 2),
        })
    return result


def compact_queries(queries: List[Dict[str, Any]], limit: int = 30) -> List[Dict[str, Any]]:
    result = []
    for q in queries[:limit]:
        result.append({
            "query": q.get("query"),
            "page": q.get("page"),
            "clicks": q.get("clicks", 0),
            "impressions": q.get("impressions", 0),
            "ctr_percent": pct(q.get("ctr", 0)),
            "position": round(float(q.get("position", 0)), 2),
        })
    return result


def build_feedback() -> Dict[str, Any]:
    pages = fetch_page_performance(row_limit=100)
    queries = fetch_query_performance(row_limit=100)

    clicked_queries = [q for q in queries if q.get("clicks", 0) > 0]
    high_impression_no_click = [
        q for q in queries
        if q.get("impressions", 0) >= 3 and q.get("clicks", 0) == 0
    ]

    best_query = clicked_queries[0]["query"] if clicked_queries else "Shibuya private stay"
    weak_query = high_impression_no_click[0]["query"] if high_impression_no_click else "Shibuya accommodation"

    summary = (
        f"Google Search Console data shows that '{best_query}' is currently the strongest search signal. "
        f"Some queries such as '{weak_query}' receive impressions but few or no clicks, so future English articles should improve title relevance and search intent matching. "
        "The blog should shift toward Shibuya-focused English SEO while mentioning Hatagaya only as the precise neighborhood within Shibuya City."
    )

    feedback = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "Google Search Console",
        "site_url": SITE_URL,
        "summary": summary,
        "good_patterns": [
            "Use Shibuya, Shibuya City, and Tokyo as the primary English SEO keywords",
            "Use practical travel-intent phrases such as private house in Shibuya, traditional house stay in Tokyo, family stay in Shibuya, quiet stay in Shibuya City, and long stay in Tokyo",
            "Mention Hatagaya only as the accurate local neighborhood inside Shibuya City",
            "Answer the traveler’s practical question first, then introduce Izumian naturally",
            f"Use currently visible search intent as a hint, especially queries related to '{best_query}'"
        ],
        "bad_patterns": [
            "Do not make Hatagaya the main SEO keyword in titles",
            "Do not imply that the property is next to Shibuya Station",
            "Do not repeat the same facility introduction about black-and-wood interior, spiral staircase, and quiet traditional house in every article",
            "Do not write vague diary-style posts without a clear travel search intent",
            "Do not rely only on Japanese search keywords if the target audience is international travelers"
        ],
        "next_prompt_instruction": (
            "Generate blog titles and articles in natural English with Shibuya as the primary SEO focus. "
            "Each article should target one clear search intent, such as 'private house in Shibuya', "
            "'traditional house stay in Tokyo', 'family stay in Shibuya City', 'quiet local stay in Shibuya', "
            "or 'long stay accommodation in Tokyo'. "
            "Hatagaya may be mentioned only as a quiet local neighborhood within Shibuya City. "
            "Do not present the property as being next to Shibuya Station. "
            "The first half of each article should answer the traveler’s question clearly, and the second half should explain why Izumian fits that need."
        ),
        "metrics": {
            "top_pages": compact_pages(pages, 20),
            "top_queries": compact_queries(queries, 30)
        }
    }

    return feedback


def main():
    feedback = build_feedback()

    os.makedirs(os.path.dirname(FEEDBACK_FILE), exist_ok=True)
    with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
        json.dump(feedback, f, ensure_ascii=False, indent=2)

    print(f"[OK] Updated prompt feedback: {FEEDBACK_FILE}")
    print(json.dumps(feedback, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
