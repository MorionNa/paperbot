# core/export/excel.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pandas as pd


def export_new_articles_to_excel(new_articles: List[Dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for a in new_articles:
        rows.append(
            {
                "published_date": a.get("published_date", ""),
                "journal": a.get("journal", ""),
                "publisher": a.get("publisher", ""),
                "title": a.get("title", ""),
                "doi": a.get("doi", ""),
                "url": a.get("url", ""),
                "authors": "; ".join(a.get("authors") or []),
                "subjects": "; ".join(a.get("subjects") or []),
                "fulltext_status": a.get("fulltext_status", ""),
                "fulltext_path": a.get("fulltext_path", ""),
            }
        )

    df = pd.DataFrame(
        rows,
        columns=[
            "published_date",
            "journal",
            "publisher",
            "title",
            "doi",
            "url",
            "authors",
            "subjects",
        ],
    )

    # 写 Excel
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="new_papers")