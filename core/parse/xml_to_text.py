from __future__ import annotations
from pathlib import Path
from typing import Tuple

from bs4 import BeautifulSoup

def _norm(s: str) -> str:
    return " ".join((s or "").split())

def parse_fulltext_file(path: Path) -> Tuple[str, str, str]:
    """
    Return (title, abstract, body_text).
    Handles: PDF / HTML / XML (JATS or non-JATS) with fallbacks.
    """
    b = path.read_bytes()

    # ---- PDF ----
    if b.startswith(b"%PDF"):
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(stream=b, filetype="pdf")
            pages = []
            for i in range(min(30, doc.page_count)):  # 先限制页数，避免太长
                pages.append(doc.load_page(i).get_text("text"))
            text = _norm("\n".join(pages))
            return "", "", text
        except Exception:
            return "", "", ""

    text = b.decode("utf-8", errors="ignore")
    head = text[:800].lower()

    # ---- HTML ----
    if "<html" in head or "<!doctype html" in head:
        soup = BeautifulSoup(text, "lxml")

        title = ""
        h1 = soup.find("h1")
        if h1:
            title = _norm(h1.get_text(" ", strip=True))
        if not title and soup.title:
            title = _norm(soup.title.get_text(" ", strip=True))

        abstract = ""
        # 常见：meta description
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            abstract = _norm(meta["content"])

        # 正文：优先 article，否则 body
        root = soup.find("article") or soup.body or soup
        paras = [_norm(p.get_text(" ", strip=True)) for p in root.find_all("p")]
        paras = [p for p in paras if p]
        body_text = "\n\n".join(paras)

        # 兜底：如果 p 很少，就拿整篇可见文本（会更噪但至少不空）
        if not body_text:
            body_text = _norm(root.get_text(" ", strip=True))

        return title, abstract, body_text

    # ---- XML ----
    soup = BeautifulSoup(text, "lxml-xml")

    # title: JATS 优先，否则 <title>
    title = ""
    t = soup.find("article-title") or soup.find("title")
    if t:
        title = _norm(t.get_text(" ", strip=True))

    # abstract
    abstract = ""
    ab = soup.find("abstract")
    if ab:
        abstract = _norm(ab.get_text(" ", strip=True))

    # body: JATS <body><p>...</p> 优先，否则所有 <p>
    paras = []
    body = soup.find("body")
    if body:
        paras = [_norm(p.get_text(" ", strip=True)) for p in body.find_all("p")]
    else:
        paras = [_norm(p.get_text(" ", strip=True)) for p in soup.find_all("p")]
    paras = [p for p in paras if p]
    body_text = "\n\n".join(paras)

    # 兜底：如果仍然空，直接取整个 XML 的可见文本（会更噪但至少有内容）
    if not body_text:
        body_text = _norm(soup.get_text(" ", strip=True))

    return title, abstract, body_text