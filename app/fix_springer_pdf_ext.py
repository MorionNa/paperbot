from pathlib import Path
import sqlite3

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "data" / "papers.db"

conn = sqlite3.connect(str(DB_PATH))
cur = conn.cursor()

rows = cur.execute("""
SELECT doi, file_path
FROM fulltexts
WHERE provider='springer' AND status='ok' AND file_path LIKE '%.xml'
""").fetchall()

fixed = 0
for doi, fp in rows:
    p = Path(fp)
    if not p.exists():
        continue
    b = p.read_bytes()
    if not b.startswith(b"%PDF"):
        continue

    new_p = p.with_suffix(".pdf")
    p.rename(new_p)

    cur.execute("""
    UPDATE fulltexts SET file_path=?, format='pdf'
    WHERE doi=?
    """, (str(new_p), doi))
    fixed += 1

conn.commit()
conn.close()
print("fixed:", fixed)