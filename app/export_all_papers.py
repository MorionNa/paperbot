# app/export_all_papers.py
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import yaml


def resolve_sqlite_path(db_url: str, base_dir: Path) -> Path:
    """
    Supports:
      - sqlite:///data/papers.db
      - sqlite:///E:/paperbot/data/papers.db
      - data/papers.db
    """
    if db_url.startswith("sqlite:"):
        u = urlparse(db_url)
        p = (u.path or "").lstrip("/")
        # Windows drive like 'E:/...'
        if len(p) >= 2 and p[1] == ":":
            return Path(p)
        return (base_dir / p).resolve()
    return (base_dir / db_url).resolve()


def json_to_joined_str(x: str, sep: str = "; ") -> str:
    if not x:
        return ""
    try:
        obj = json.loads(x)
        if isinstance(obj, list):
            return sep.join(str(i) for i in obj)
        return str(obj)
    except Exception:
        return str(x)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--print", action="store_true", help="Print all rows to console (may be huge)")
    parser.add_argument("--out", default="", help="Output file path (xlsx/csv). Default auto in outputs/")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parents[1]  # project root
    cfg_path = base_dir / "config" / "config.yml"

    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    db_url = cfg["pipeline"]["db_url"]
    db_path = resolve_sqlite_path(db_url, base_dir)
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    conn = sqlite3.connect(str(db_path))

    # 读出全部文献
    df = pd.read_sql_query(
        """
        SELECT
          doi, title, journal, publisher, published_date, url,
          authors_json, subjects_json, type, issn_json, inserted_at
        FROM articles
        ORDER BY inserted_at DESC;
        """,
        conn,
    )
    conn.close()

    # 美化 JSON 字段
    if "authors_json" in df.columns:
        df["authors"] = df["authors_json"].apply(lambda x: json_to_joined_str(x))
    if "subjects_json" in df.columns:
        df["subjects"] = df["subjects_json"].apply(lambda x: json_to_joined_str(x))
    if "issn_json" in df.columns:
        df["issn"] = df["issn_json"].apply(lambda x: json_to_joined_str(x))

    # 调整列顺序（保留原 json 列也行；这里默认不输出 json 原列）
    out_df = df[
        [
            "published_date",
            "journal",
            "publisher",
            "title",
            "doi",
            "url",
            "authors",
            "subjects",
            "type",
            "issn",
            "inserted_at",
        ]
    ].copy()

    # 输出文件名
    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = (base_dir / out_path).resolve()
    else:
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        out_path = (base_dir / "outputs" / f"all_papers_{ts}.xlsx").resolve()

    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 写文件（xlsx 或 csv）
    if out_path.suffix.lower() == ".csv":
        out_df.to_csv(out_path, index=False, encoding="utf-8-sig")
    else:
        out_df.to_excel(out_path, index=False, sheet_name="articles")

    print(f"Exported {len(out_df)} records to: {out_path}")

    # 可选：打印全部到终端
    if args.print:
        pd.set_option("display.max_rows", None)
        pd.set_option("display.max_colwidth", 120)
        print(out_df.to_string(index=False))


if __name__ == "__main__":
    main()