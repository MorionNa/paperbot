# infra/db.py
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from typing import Any, Dict, List, Optional


def _resolve_sqlite_path(db_url: str, base_dir: Path) -> Path:
    """
    Supports:
      - sqlite:///data/papers.db  (recommended)
      - sqlite:///E:/paperbot/data/papers.db
      - data/papers.db (also ok)
    """
    if db_url.startswith("sqlite:"):
        u = urlparse(db_url)
        p = (u.path or "").lstrip("/")  # '/data/papers.db' -> 'data/papers.db'
        # handle Windows drive like 'E:/...'
        if len(p) >= 2 and p[1] == ":":
            return Path(p)
        return (base_dir / p).resolve()
    # fallback: treat as path
    return (base_dir / db_url).resolve()


def connect_sqlite(db_url: str, base_dir: Path) -> sqlite3.Connection:
    db_path = _resolve_sqlite_path(db_url, base_dir)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def init_db(conn: sqlite3.Connection) -> None:
    # language=SQLite
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS articles (
            doi TEXT PRIMARY KEY,
            title TEXT,
            journal TEXT,
            publisher TEXT,
            published_date TEXT,
            url TEXT,
            authors_json TEXT,
            subjects_json TEXT,
            type TEXT,
            issn_json TEXT,
            raw_json TEXT,
            inserted_at TEXT DEFAULT (datetime('now'))
        );
        """
    )
    # language=SQLite
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fulltexts (
            doi TEXT PRIMARY KEY,
            provider TEXT,
            format TEXT,            -- xml/pdf/html
            file_path TEXT,
            sha256 TEXT,
            status TEXT,            -- ok/failed/skipped
            http_status INTEGER,
            error TEXT,
            downloaded_at TEXT DEFAULT (datetime('now'))
        );
        """
    )
    # language=SQLite
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS parsed_texts (
            doi TEXT PRIMARY KEY,
            title TEXT,
            abstract TEXT,
            body_text TEXT,
            parsed_at TEXT DEFAULT (datetime('now')),
            parser_version TEXT
        );
        """
    )
    # language=SQLite
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS summaries (
            doi TEXT PRIMARY KEY,
            model TEXT,
            method_summary TEXT,
            result_summary TEXT,
            keywords_json TEXT,
            tags_json TEXT,
            summary_json TEXT,
            status TEXT,          -- ok/failed
            error TEXT,
            summarized_at TEXT DEFAULT (datetime('now'))
        );
        """
    )
    conn.commit()




def insert_articles(conn: sqlite3.Connection, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Insert with DOI de-duplication (INSERT OR IGNORE). Returns newly inserted articles only.
    """
    inserted: List[Dict[str, Any]] = []
    sql = """
    INSERT OR IGNORE INTO articles
    (doi, title, journal, publisher, published_date, url,
     authors_json, subjects_json, type, issn_json, raw_json)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """
    for a in articles:
        doi = (a.get("doi") or "").strip()
        if not doi:
            continue

        authors_json = json.dumps(a.get("authors") or [], ensure_ascii=False)
        subjects_json = json.dumps(a.get("subjects") or [], ensure_ascii=False)
        issn_json = json.dumps(a.get("issn") or [], ensure_ascii=False)
        raw_json = json.dumps(a.get("raw") or {}, ensure_ascii=False)

        cur = conn.execute(
            sql,
            (
                doi,
                (a.get("title") or "").strip(),
                (a.get("journal") or "").strip(),
                (a.get("publisher") or "").strip(),
                (a.get("published_date") or "").strip(),
                (a.get("url") or "").strip(),
                authors_json,
                subjects_json,
                (a.get("type") or "").strip(),
                issn_json,
                raw_json,
            ),
        )
        # rowcount == 1 means inserted; 0 means ignored (already exists)
        if cur.rowcount == 1:
            inserted.append(a)

    conn.commit()
    return inserted


def list_articles_missing_fulltext(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """
    Return articles that still need fulltext download from the DB perspective.
    """
    rows = conn.execute(
        """
        SELECT
            a.doi,
            a.title,
            a.journal,
            a.publisher,
            a.published_date,
            a.url,
            a.authors_json,
            a.subjects_json,
            a.type,
            a.issn_json,
            a.raw_json,
            f.status,
            f.file_path
        FROM articles a
        LEFT JOIN fulltexts f ON f.doi = a.doi
        WHERE f.doi IS NULL
           OR COALESCE(LOWER(f.status), '') != 'ok'
           OR COALESCE(TRIM(f.file_path), '') = '';
        """
    ).fetchall()

    result: List[Dict[str, Any]] = []
    for row in rows:
        (
            doi,
            title,
            journal,
            publisher,
            published_date,
            url,
            authors_json,
            subjects_json,
            typ,
            issn_json,
            raw_json,
            fulltext_status,
            fulltext_path,
        ) = row
        result.append(
            {
                "doi": doi or "",
                "title": title or "",
                "journal": journal or "",
                "publisher": publisher or "",
                "published_date": published_date or "",
                "url": url or "",
                "authors": json.loads(authors_json or "[]"),
                "subjects": json.loads(subjects_json or "[]"),
                "type": typ or "",
                "issn": json.loads(issn_json or "[]"),
                "raw": json.loads(raw_json or "{}"),
                "fulltext_status": fulltext_status or "",
                "fulltext_path": fulltext_path or "",
            }
        )
    return result


def resolve_fulltext_status(status: Optional[str], file_path: Optional[str]) -> str:
    normalized = (status or "").strip().lower()
    path_text = (file_path or "").strip()
    if normalized in ("ok", "success", "downloaded"):
        if not path_text:
            return "missing_file"
        if not Path(path_text).exists():
            return "missing_file"
        return "ok"
    return normalized or ""


def get_fulltext_status(conn: sqlite3.Connection, doi: str) -> Optional[str]:
    cur = conn.execute("SELECT status, file_path FROM fulltexts WHERE doi = ?;", (doi,))
    row = cur.fetchone()
    return resolve_fulltext_status(row[0], row[1]) if row else None

def upsert_fulltext(conn: sqlite3.Connection, doi: str, rec: Dict[str, Any]) -> None:
    """
    Insert or update a fulltext record for a DOI.
    """
    conn.execute(
        """
        INSERT INTO fulltexts
        (doi, provider, format, file_path, sha256, status, http_status, error, downloaded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(doi) DO UPDATE SET
          provider=excluded.provider,
          format=excluded.format,
          file_path=excluded.file_path,
          sha256=excluded.sha256,
          status=excluded.status,
          http_status=excluded.http_status,
          error=excluded.error,
          downloaded_at=excluded.downloaded_at;
        """,
        (
            doi,
            rec.get("provider"),
            rec.get("format"),
            rec.get("file_path"),
            rec.get("sha256"),
            rec.get("status"),
            rec.get("http_status"),
            rec.get("error"),
            rec.get("downloaded_at") or datetime.now().isoformat(timespec="seconds"),
        ),
    )
    conn.commit()

def list_fulltexts_ok(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    cur = conn.execute(
        """
        SELECT doi, file_path, status
        FROM fulltexts
        WHERE COALESCE(TRIM(file_path), '') != '';
        """
    )
    rows = cur.fetchall()
    return [(doi, file_path) for doi, file_path, status in rows if resolve_fulltext_status(status, file_path) == "ok"]


def delete_papers_by_dois(conn: sqlite3.Connection, dois: List[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for doi in dois:
        d = (doi or "").strip()
        if not d or d in seen:
            continue
        seen.add(d)
        normalized.append(d)

    if not normalized:
        return []

    placeholders = ",".join(["?"] * len(normalized))
    rows = conn.execute(
        f"""
        SELECT file_path
        FROM fulltexts
        WHERE doi IN ({placeholders});
        """,
        normalized,
    ).fetchall()
    file_paths = [str(row[0] or "").strip() for row in rows if str(row[0] or "").strip()]

    conn.execute(f"DELETE FROM summaries WHERE doi IN ({placeholders});", normalized)
    conn.execute(f"DELETE FROM parsed_texts WHERE doi IN ({placeholders});", normalized)
    conn.execute(f"DELETE FROM fulltexts WHERE doi IN ({placeholders});", normalized)
    conn.execute(f"DELETE FROM articles WHERE doi IN ({placeholders});", normalized)
    conn.commit()
    return file_paths

def upsert_parsed_text(conn: sqlite3.Connection, doi: str, title: str, abstract: str, body_text: str, parser_version: str) -> None:
    conn.execute(
        """
        INSERT INTO parsed_texts (doi, title, abstract, body_text, parser_version)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(doi) DO UPDATE SET
          title=excluded.title,
          abstract=excluded.abstract,
          body_text=excluded.body_text,
          parsed_at=datetime('now'),
          parser_version=excluded.parser_version;
        """,
        (doi, title, abstract, body_text, parser_version),
    )
    conn.commit()
