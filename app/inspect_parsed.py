from pathlib import Path
import sqlite3

BASE_DIR = Path(__file__).resolve().parents[1]   # E:\paperbot
DB_PATH = BASE_DIR / "data" / "papers.db"

print("DB_PATH =", DB_PATH)
print("exists  =", DB_PATH.exists())

conn = sqlite3.connect(str(DB_PATH))
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM parsed_texts;")
print("parsed_texts rows:", cur.fetchone()[0])

cur.execute("""
SELECT doi, length(abstract), length(body_text), substr(title,1,60)
FROM parsed_texts
ORDER BY parsed_at DESC
LIMIT 10;
""")
for r in cur.fetchall():
    print(r)

conn.close()