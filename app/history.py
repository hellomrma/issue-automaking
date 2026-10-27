"""생성 이력 저장 (SQLite)"""
import logging
import os
import re
import sqlite3
from contextlib import closing
from datetime import datetime
from typing import Optional

logger = logging.getLogger("app.history")

# 이력 DB 경로. 환경변수 HISTORY_DB 로 변경 가능
DB_PATH = os.getenv("HISTORY_DB") or os.path.join(os.path.dirname(__file__), "..", "data", "history.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    mode TEXT NOT NULL,          -- keyword | url
    keyword TEXT,
    source_url TEXT,
    style TEXT,
    length TEXT,
    title TEXT NOT NULL DEFAULT '',
    markdown TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_articles_keyword ON articles(keyword);
"""

_LIST_COLUMNS = "id, created_at, updated_at, mode, keyword, source_url, style, length, title"


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def extract_title(markdown: str) -> str:
    """첫 번째 # 제목 줄을 글 제목으로 사용"""
    m = re.search(r"^#\s+(.+)$", markdown or "", re.MULTILINE)
    return m.group(1).strip()[:200] if m else ""


def create(*, mode: str, keyword: Optional[str] = None, source_url: Optional[str] = None,
           style: Optional[str] = None, length: Optional[str] = None, markdown: str = "") -> int:
    """이력 추가 후 id 반환"""
    now = _now()
    with closing(_connect()) as conn, conn:
        cur = conn.execute(
            "INSERT INTO articles (created_at, updated_at, mode, keyword, source_url, style, length, title, markdown)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (now, now, mode, keyword, source_url, style, length, extract_title(markdown), markdown),
        )
        return cur.lastrowid


def update_markdown(article_id: int, markdown: str) -> bool:
    """본문(과 제목) 갱신. 대상이 없으면 False"""
    with closing(_connect()) as conn, conn:
        cur = conn.execute(
            "UPDATE articles SET markdown = ?, title = ?, updated_at = ? WHERE id = ?",
            (markdown, extract_title(markdown), _now(), article_id),
        )
        return cur.rowcount > 0


def get(article_id: int) -> Optional[dict]:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
        return dict(row) if row else None


def list_recent(query: Optional[str] = None, limit: int = 30) -> list[dict]:
    """최근 글 목록 (본문 제외). query가 있으면 제목·키워드에서 검색"""
    sql = f"SELECT {_LIST_COLUMNS} FROM articles WHERE markdown != ''"
    params: list = []
    if query:
        sql += " AND (title LIKE ? OR keyword LIKE ?)"
        params += [f"%{query}%", f"%{query}%"]
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with closing(_connect()) as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def find_by_keyword(keyword: str, limit: int = 5) -> list[dict]:
    """같은 키워드(공백·대소문자 무시)로 쓴 글"""
    normalized = re.sub(r"\s+", "", keyword).lower()
    with closing(_connect()) as conn:
        rows = conn.execute(
            f"SELECT {_LIST_COLUMNS} FROM articles"
            " WHERE markdown != '' AND lower(replace(keyword, ' ', '')) = ? ORDER BY id DESC LIMIT ?",
            (normalized, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def delete(article_id: int) -> bool:
    with closing(_connect()) as conn, conn:
        return conn.execute("DELETE FROM articles WHERE id = ?", (article_id,)).rowcount > 0
