import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
db = BASE / "data" / "papers.db"
conn = sqlite3.connect(str(db))
cur = conn.cursor()

cur.execute("SELECT status, COUNT(*) FROM summaries GROUP BY status;")
print(cur.fetchall())

cur.execute("""
SELECT doi, substr(method_summary,1,80), substr(result_summary,1,80)
FROM summaries
ORDER BY summarized_at DESC
LIMIT 5;
""")
for r in cur.fetchall():
    print(r)

conn.close()