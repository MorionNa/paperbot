from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path
from urllib.parse import quote

import requests
import fitz  # PyMuPDF
import yaml

from infra.secrets import load_secrets_into_env
from core.download.link_fetcher import doi_sha1


def pick_one_elsevier_doi(db_path: Path) -> str | None:
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        """
        SELECT doi
        FROM fulltexts
        WHERE provider='elsevier' AND status='ok' AND (format='xml' OR file_path LIKE '%.xml')
        ORDER BY downloaded_at DESC
        LIMIT 1;
        """
    ).fetchone()
    conn.close()
    return row[0] if row else None


def classify_pdf(pdf_path: Path) -> dict:
    size_kb = pdf_path.stat().st_size / 1024.0
    doc = fitz.open(str(pdf_path))
    pages = doc.page_count
    # 抽取前两页少量文本用于判断（不打印太多）
    txt = ""
    for i in range(min(2, pages)):
        txt += doc.load_page(i).get_text("text") + "\n"
    doc.close()

    # 粗判：1页且很小 → 很可能是预览页（但极少数短文可能确实只有1页）
    likely_preview = (pages <= 1 and size_kb < 300)

    return {
        "pages": pages,
        "size_kb": round(size_kb, 1),
        "likely_preview": likely_preview,
        "text_head": txt[:400].replace("\n", " ").strip(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--doi", default="", help="Specify a DOI like 10.1016/j.aei.2026.104363")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parents[1]
    load_secrets_into_env(base_dir)

    cfg = yaml.safe_load((base_dir / "config" / "config.yml").read_text(encoding="utf-8"))
    db_path = base_dir / "data" / "papers.db"

    api_key = os.getenv("ELSEVIER_API_KEY", "").strip()
    insttoken = os.getenv("ELSEVIER_INSTTOKEN", "").strip()  # 没有就留空
    if not api_key:
        raise RuntimeError("Missing ELSEVIER_API_KEY (check secrets.yml mapping/loading)")

    doi = args.doi.strip() or pick_one_elsevier_doi(db_path)
    if not doi:
        raise RuntimeError("No elsevier XML record found in DB. Provide --doi or run daily first.")

    doi_enc = quote(doi, safe="")
    url_pdf = f"https://api.elsevier.com/content/article/doi/{doi_enc}?httpAccept=application/pdf"

    headers = {
        "X-ELS-APIKey": api_key,
        "Accept": "application/pdf",
        "User-Agent": "paperbot/0.1 (elsevier-pdf-test)",
    }
    # 只有你确认 insttoken 正确绑定 APIKey 时才建议带，否则会 401
    if insttoken:
        headers["X-ELS-Insttoken"] = insttoken

    out_dir = base_dir / "data" / "fulltext" / "elsevier_pdf_test"
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / f"{doi_sha1(doi)}.pdf"

    print("Testing DOI:", doi)
    print("GET:", url_pdf)

    r = requests.get(url_pdf, headers=headers, timeout=(10, 30), stream=True)
    print("HTTP:", r.status_code)
    print("Content-Type:", r.headers.get("Content-Type"))
    if r.status_code != 200:
        body_head = r.text[:200] if r.text else ""
        print("Body head:", body_head)
        return

    # 保存 PDF
    with open(pdf_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=1024 * 128):
            if chunk:
                f.write(chunk)

    # 校验 PDF 是否真的为 PDF
    head = pdf_path.read_bytes()[:5]
    if head != b"%PDF-":
        print("Downloaded file is not a PDF. Head:", head)
        print("Saved to:", pdf_path)
        return

    info = classify_pdf(pdf_path)
    print("Saved to:", pdf_path)
    print("Pages:", info["pages"])
    print("Size(KB):", info["size_kb"])
    print("Likely preview:", info["likely_preview"])
    print("Text head:", info["text_head"])


if __name__ == "__main__":
    main()