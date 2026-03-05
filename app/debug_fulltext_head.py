from pathlib import Path
import sqlite3

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "data" / "papers.db"

conn = sqlite3.connect(str(DB_PATH))
doi, fp = conn.execute(
    "SELECT doi, file_path FROM fulltexts WHERE status='ok' AND file_path!='' LIMIT 1;"
).fetchone()
conn.close()

p = Path(fp)
b = p.read_bytes()

print("DOI:", doi)
print("Path:", p)
print("First 20 bytes:", b[:20])

# quick type detection
if b.startswith(b"%PDF"):
    print("Detected: PDF")
else:
    s = b[:500].decode("utf-8", errors="ignore").lower()
    if "<html" in s or "<!doctype html" in s:
        print("Detected: HTML")
    elif "<?xml" in s or "<article" in s or "<body" in s:
        print("Detected: XML-ish")
    else:
        print("Detected: Unknown/Text")
        print("Head preview:", repr(s[:200]))