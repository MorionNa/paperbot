# core/download/crossref_tdm.py
from __future__ import annotations

import hashlib
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests


@dataclass
class DownloadConfig:
    timeout_sec: int = 60
    polite_sleep_sec: float = 1.0
    # XML 优先：如果同一 DOI 有多个 text-mining 链接，优先选择含 xml 的 content-type
    prefer_xml: bool = True
    user_agent: str = "paperbot/0.1 (fulltext-downloader)"


def _doi_to_fname(doi: str) -> str:
    h = hashlib.sha1(doi.encode("utf-8")).hexdigest()
    return h


def pick_text_mining_xml_link(raw: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """
    Return (url, content_type) for best text-mining link, preferring XML.
    Crossref item may contain raw["link"] list.
    """
    links = raw.get("link") or []
    if not isinstance(links, list) or not links:
        return None

    candidates = []
    for lk in links:
        if not isinstance(lk, dict):
            continue
        if (lk.get("intended-application") or "").lower() != "text-mining":
            continue
        url = lk.get("URL") or lk.get("url")
        ctype = (lk.get("content-type") or lk.get("content_type") or "").lower()
        if url:
            candidates.append((url, ctype))

    if not candidates:
        return None

    # XML 优先：content-type 里包含 xml（如 application/xml, application/vnd.jats+xml 等）
    xml_first = [c for c in candidates if "xml" in (c[1] or "")]
    if xml_first:
        return xml_first[0]
    return candidates[0]


def download_xml_via_url(
    doi: str,
    url: str,
    out_dir: Path,
    cfg: DownloadConfig,
    session: Optional[requests.Session] = None,
) -> Dict[str, Any]:
    """
    Download XML to data/fulltext/crossref/<sha1>.xml
    Returns record dict for DB.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = _doi_to_fname(doi) + ".xml"
    fpath = out_dir / fname
    tmp_path = out_dir / (fname + ".part")

    sess = session or requests.Session()
    headers = {"User-Agent": cfg.user_agent}

    try:
        r = sess.get(url, headers=headers, timeout=cfg.timeout_sec, stream=True)
        http_status = r.status_code

        if http_status != 200:
            return {
                "provider": "crossref",
                "format": "xml",
                "file_path": "",
                "sha256": "",
                "status": "failed",
                "http_status": http_status,
                "error": f"HTTP {http_status}",
            }

        ctype = (r.headers.get("Content-Type") or "").lower()
        # 很多会是 application/xml / application/vnd.jats+xml；如果不是 xml 也先保存，后续你再决定是否丢弃
        # 这里做一个轻量提醒
        if "xml" not in ctype:
            # 仍然保存，但标注一下
            note = f"Downloaded but content-type not xml: {ctype}"
        else:
            note = ""

        sha256 = hashlib.sha256()
        with open(tmp_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 128):
                if not chunk:
                    continue
                f.write(chunk)
                sha256.update(chunk)

        os.replace(tmp_path, fpath)  # 原子替换
        time.sleep(cfg.polite_sleep_sec)

        return {
            "provider": "crossref",
            "format": "xml",
            "file_path": str(fpath),
            "sha256": sha256.hexdigest(),
            "status": "ok",
            "http_status": http_status,
            "error": note,
        }

    except Exception as e:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        return {
            "provider": "crossref",
            "format": "xml",
            "file_path": "",
            "sha256": "",
            "status": "failed",
            "http_status": None,
            "error": repr(e),
        }