from __future__ import annotations

import random
import sqlite3
from pathlib import Path


def main():
    base_dir = Path(__file__).resolve().parents[1]  # E:\paperbot
    db_path = base_dir / "data" / "papers.db"

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # 随机抽一篇：优先抽 body_text 非空的
    rows = cur.execute(
        """
        SELECT doi, title, abstract, body_text
        FROM parsed_texts
        WHERE body_text IS NOT NULL AND length(body_text) > 0
        """
    ).fetchall()

    if not rows:
        print("No non-empty body_text found in parsed_texts.")
        conn.close()
        return

    doi, title, abstract, body_text = random.choice(rows)

    print("DOI:", doi)
    print("title_len:", len(title or ""))
    print("abstract_len:", len(abstract or ""))
    print("body_len:", len(body_text or ""))

    if title:
        print("\n=== TITLE ===")
        print(title)

    if abstract:
        print("\n=== ABSTRACT (first 500 chars) ===")
        print((abstract[:500] + ("..." if len(abstract) > 500 else "")))

    print("\n=== BODY (first 1000 chars) ===")
    preview = (body_text[:1000] + ("..." if len(body_text) > 1000 else ""))
    print(preview)

    conn.close()


if __name__ == "__main__":
    main()