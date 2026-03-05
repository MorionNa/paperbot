# core/summarize/chunking.py
from __future__ import annotations

from typing import List


def chunk_text(text: str, max_chars: int = 12000, overlap: int = 300) -> List[str]:
    """
    简单按字符分块（PDF 抽取文本用这个足够先跑起来）。
    """
    text = (text or "").strip()
    if not text:
        return []
    chunks = []
    i = 0
    n = len(text)
    while i < n:
        j = min(n, i + max_chars)
        chunks.append(text[i:j])
        if j == n:
            break
        i = max(0, j - overlap)
    return chunks