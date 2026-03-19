# app/parse_fulltexts.py
from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import urlparse

import yaml

from infra.db import connect_sqlite, init_db, list_fulltexts_ok, upsert_parsed_text
from core.parse.xml_to_text import parse_fulltext_file


PARSER_VERSION = "jats_bs4_v1"


def main():
    base_dir = Path(__file__).resolve().parents[1]
    cfg_path = base_dir / "config" / "config.yml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    conn = connect_sqlite(cfg["pipeline"]["db_url"], base_dir)
    init_db(conn)

    rows = list_fulltexts_ok(conn)
    print(f"fulltexts ok: {len(rows)}")

    done = 0
    for doi, file_path in rows:
        p = Path(file_path)
        if not p.exists():
            continue
        title, abstract, body_text = parse_fulltext_file(p)
        upsert_parsed_text(conn, doi, title, abstract, body_text, PARSER_VERSION)
        done += 1
        print(f"[{done}/{len(rows)}] parsed {doi} (len={len(body_text)})", flush=True)

    conn.close()
    print(f"parsed_success_count: {done}")
    print("Done.")


if __name__ == "__main__":
    main()