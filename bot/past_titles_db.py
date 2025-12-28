import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from difflib import SequenceMatcher
from typing import List, Tuple

DB_PATH = os.environ.get("PAST_TITLES_DB_PATH", "past_titles.sqlite3")
SIMILARITY_THRESHOLD = float(os.environ.get("TITLE_SIMILARITY_THRESHOLD", "0.85"))
MAX_PAST_TITLES = int(os.environ.get("MAX_PAST_TITLES", "2000"))


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS titles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def add_title(title: str):
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO titles (title, created_at) VALUES (?, ?)",
            (title, now),
        )
        conn.commit()


def fetch_recent_titles(limit: int = MAX_PAST_TITLES) -> List[Tuple[int, str]]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, title FROM titles ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return cur.fetchall()


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def find_similar_titles(candidate: str, threshold: float = SIMILARITY_THRESHOLD) -> List[str]:
    similar: List[str] = []
    for _, past_title in fetch_recent_titles():
        if similarity(candidate, past_title) >= threshold:
            similar.append(past_title)
    return similar
