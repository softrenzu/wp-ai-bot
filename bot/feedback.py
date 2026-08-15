import html
import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from analytics import fetch_page_performance, fetch_query_performance


OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")

SITE_URL = os.environ.get("SEARCH_CONSOLE_SITE_URL", "https://staytokyo.xyz/").rstrip("/")
FEEDBACK_FILE = os.environ.get("PROMPT_FEEDBACK_FILE", "/secrets/prompt_feedback.json")


def pct(value: float) -> float:
    return round(float(value or 0) * 100, 2)


def strip_html(text: str) -> str:
    text = html.unescape(text or "")
    soup = BeautifulSoup(text, "html.parser")
    clean = soup.get_text(" ")
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def extract_post_id(url: str) -> Optional[int]:
    m = re.search(r"/archives/(\d+)", url or "")
    if not m:
        return None
    return int(m.group(1))


def fetch_wp_post(url: str) -> Dict[str, Any]:
    post_id = extract_post_id(url)
    if not post_id:
        return {
            "url": url,
            "post_id": None,
            "title": "",
            "excerpt": "",
            "content": "",
            "date": "",
        }

    api_url = f"{SITE_URL}/wp-json/wp/v2/posts/{post_id}"

    try:
        resp = requests.get(api_url, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        title = strip_html((data.get("title") or {}).get("rendered", ""))
        excerpt = strip_html((data.get("excerpt") or {}).get("rendered", ""))
        content = strip_html((data.get("content") or {}).get("rendered", ""))

        return {
            "url": url,
            "post_id": post_id,
            "title": title,
            "excerpt": excerpt[:500],
            "content": content[:3000],
            "date": data.get("date", ""),
        }
    except Exception as e:
        return {
            "url": url,
            "post_id": post_id,
            "title": "",
            "excerpt": "",
            "content": "",
            "date": "",
            "error": str(e),
        }


def enrich_pages(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    enriched = []

    for p in pages:
        item = dict(p)
        wp = fetch_wp_post(p.get("page", ""))

        item.update({
            "post_id": wp.get("post_id"),
            "title": wp.get("title", ""),
            "excerpt": wp.get("excerpt", ""),
            "content": wp.get("content", ""),
            "date": wp.get("date", ""),
        })

        enriched.append(item)

    return enriched


def compact_page(p: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "page": p.get("page"),
        "post_id": p.get("post_id"),
        "title": p.get("title"),
        "date": p.get("date"),
        "clicks": p.get("clicks", 0),
        "impressions": p.get("impressions", 0),
        "ctr_percent": pct(p.get("ctr", 0)),
        "position": round(float(p.get("position", 0)), 2),
        "excerpt": p.get("excerpt", ""),
        "content_sample": p.get("content", "")[:1200],
    }


def compact_query(q: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "query": q.get("query"),
        "page": q.get("page"),
        "clicks": q.get("clicks", 0),
        "impressions": q.get("impressions", 0),
        "ctr_percent": pct(q.get("ctr", 0)),
        "position": round(float(q.get("position", 0)), 2),
    }


def classify_pages(pages: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    winners = [
        p for p in pages
        if p.get("clicks", 0) > 0
    ]

    underperformers = [
        p for p in pages
        if p.get("impressions", 0) >= 5 and p.get("clicks", 0) == 0
    ]

    winners.sort(key=lambda x: (x.get("clicks", 0), x.get("impressions", 0)), reverse=True)
    underperformers.sort(key=lambda x: (x.get("impressions", 0), -float(x.get("position", 99))), reverse=True)

    return {
        "winners": winners[:8],
        "underperformers": underperformers[:8],
    }


def call_openai_analysis(
    winners: List[Dict[str, Any]],
    underperformers: List[Dict[str, Any]],
    queries: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not OPENAI_API_KEY:
        return None

    prompt = f"""
You are an SEO analyst for staytokyo.xyz, a WordPress site for Izumian, a private traditional-style accommodation in Hatagaya, Shibuya City, Tokyo.

Goal:
Analyze Search Console data plus WordPress article titles/body, then update the article-generation prompt feedback.

Important strategy:
- Future blog articles should be in natural English.
- Main SEO focus: Shibuya / Shibuya City / Tokyo.
- Hatagaya should be mentioned only as the accurate neighborhood within Shibuya City.
- Do not imply that the property is next to Shibuya Station.
- We want a real feedback loop:
  Search Console → winning/weak articles → article title/body analysis → reason → prompt improvement → next article.

Winning pages:
{json.dumps([compact_page(p) for p in winners], ensure_ascii=False, indent=2)}

Underperforming pages:
{json.dumps([compact_page(p) for p in underperformers], ensure_ascii=False, indent=2)}

Top queries:
{json.dumps([compact_query(q) for q in queries[:40]], ensure_ascii=False, indent=2)}

Return JSON only with this structure:
{{
  "summary": "1-3 sentence analysis summary",
  "why_winners_worked": ["reason", "..."],
  "why_underperformers_failed": ["reason", "..."],
  "good_patterns": ["pattern to reuse", "..."],
  "bad_patterns": ["pattern to avoid", "..."],
  "next_prompt_instruction": "Concrete instruction to insert into the next article-generation prompt",
  "next_article_ideas": ["English SEO article idea", "..."],
  "experiment_plan": "One experiment to run next week"
}}
""".strip()

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENAI_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": "You analyze SEO data and return strict JSON only.",
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                "temperature": 0.2,
                "max_tokens": 1800,
            },
            timeout=60,
        )
        resp.raise_for_status()

        text = resp.json()["choices"][0]["message"]["content"].strip()
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"^```\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

        data = json.loads(text)
        if isinstance(data, dict):
            return data

    except Exception as e:
        print(f"[WARN] OpenAI SEO analysis failed: {e}")

    return None


def fallback_analysis(
    winners: List[Dict[str, Any]],
    underperformers: List[Dict[str, Any]],
    queries: List[Dict[str, Any]],
) -> Dict[str, Any]:
    clicked_queries = [q for q in queries if q.get("clicks", 0) > 0]
    no_click_queries = [
        q for q in queries
        if q.get("impressions", 0) >= 3 and q.get("clicks", 0) == 0
    ]

    best_query = clicked_queries[0]["query"] if clicked_queries else "Shibuya private stay"
    weak_query = no_click_queries[0]["query"] if no_click_queries else "Shibuya accommodation"

    return {
        "summary": (
            f"Search Console currently shows '{best_query}' as the strongest signal, while '{weak_query}' has impressions but weak clicks. "
            "Future posts should use English Shibuya-focused travel intent and avoid vague facility introductions."
        ),
        "why_winners_worked": [
            "Winning pages appear to match concrete location-based search intent.",
            "Pages with clearer relation to accommodation or local stay are more likely to receive clicks.",
        ],
        "why_underperformers_failed": [
            "Some pages receive impressions but do not give users a clear reason to click.",
            "Facility-only or vague titles likely fail to match search intent strongly enough.",
        ],
        "good_patterns": [
            "Use Shibuya, Shibuya City, and Tokyo as primary English SEO keywords.",
            "Use practical phrases such as private house in Shibuya, traditional house stay in Tokyo, quiet stay in Shibuya City, and family stay near Shinjuku.",
            "Answer the traveler's practical question before introducing Izumian.",
        ],
        "bad_patterns": [
            "Do not make Hatagaya the main SEO keyword in English titles.",
            "Do not imply that Izumian is next to Shibuya Station.",
            "Do not repeat the same black-and-wood interior and spiral staircase introduction in every article.",
            "Do not write vague diary-style posts without a search intent.",
        ],
        "next_prompt_instruction": (
            "Write English articles with Shibuya as the primary SEO focus. "
            "Each article must target one clear search intent, such as private house in Shibuya, traditional house stay in Tokyo, family stay in Shibuya City, quiet local stay in Shibuya, or long stay accommodation in Tokyo. "
            "Mention Hatagaya only as the accurate neighborhood inside Shibuya City. "
            "Do not suggest the property is next to Shibuya Station. "
            "Start by answering the traveler's question, then explain why Izumian fits."
        ),
        "next_article_ideas": [
            "Private House in Shibuya for a Quiet Tokyo Stay",
            "Traditional House Stay in Tokyo: A Local Base in Shibuya City",
            "Family Stay in Shibuya City: What to Know Before Booking",
            "Long Stay Accommodation in Tokyo Near Shinjuku and Shibuya",
        ],
        "experiment_plan": "Next week, test practical guide-style English articles that answer one traveler question in the first 300 words.",
    }


def build_feedback() -> Dict[str, Any]:
    pages = fetch_page_performance(row_limit=100)
    queries = fetch_query_performance(row_limit=100)

    enriched_pages = enrich_pages(pages)
    classified = classify_pages(enriched_pages)

    winners = classified["winners"]
    underperformers = classified["underperformers"]

    analysis = call_openai_analysis(winners, underperformers, queries)
    if not analysis:
        analysis = fallback_analysis(winners, underperformers, queries)

    feedback = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "Google Search Console + WordPress REST API + AI analysis",
        "site_url": SITE_URL,
        "summary": analysis.get("summary", ""),
        "why_winners_worked": analysis.get("why_winners_worked", []),
        "why_underperformers_failed": analysis.get("why_underperformers_failed", []),
        "good_patterns": analysis.get("good_patterns", []),
        "bad_patterns": analysis.get("bad_patterns", []),
        "next_prompt_instruction": analysis.get("next_prompt_instruction", ""),
        "next_article_ideas": analysis.get("next_article_ideas", []),
        "experiment_plan": analysis.get("experiment_plan", ""),
        "metrics": {
            "winners": [compact_page(p) for p in winners],
            "underperformers": [compact_page(p) for p in underperformers],
            "top_queries": [compact_query(q) for q in queries[:40]],
        },
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
