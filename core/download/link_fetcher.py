# core/download/link_fetcher.py
from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests


@dataclass
class DownloadConfig:
    timeout_sec: int = 20
    polite_sleep_sec: float = 0.2
    prefer_xml: bool = True
    user_agent: str = "paperbot/0.1 (fulltext-downloader)"


def doi_sha1(doi: str) -> str:
    return hashlib.sha1(doi.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 128), b""):
            h.update(chunk)
    return h.hexdigest()


def pick_text_mining_link(raw: Dict[str, Any], prefer_xml: bool = True) -> Optional[Tuple[str, str]]:
    """
    Return (url, content_type) for best text-mining link.
    Prefer XML when possible.
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

    if prefer_xml:
        xml_first = [c for c in candidates if "xml" in (c[1] or "")]
        if xml_first:
            return xml_first[0]
    return candidates[0]


def download_via_url(
    doi: str,
    url: str,
    out_dir: Path,
    cfg: DownloadConfig,
    session: Optional[requests.Session] = None,
    extra_headers: Optional[Dict[str, str]] = None,
    expected_ext: str = ".xml",
) -> Dict[str, Any]:
    """
    Download content to data/fulltext/<provider>/<sha1>.xml (default).
    Returns a dict suitable for upsert_fulltext().
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = doi_sha1(doi) + expected_ext
    fpath = out_dir / fname
    tmp_path = out_dir / (fname + ".part")

    sess = session or requests.Session()
    headers = {"User-Agent": cfg.user_agent}
    if extra_headers:
        headers.update(extra_headers)

    try:
        # timeout=(connect_timeout, read_timeout)
        r = sess.get(url, headers=headers, timeout=(10, cfg.timeout_sec), stream=True)
        http_status = r.status_code

        if http_status != 200:
            return {
                "format": expected_ext.lstrip("."),
                "file_path": "",
                "sha256": "",
                "status": "failed",
                "http_status": http_status,
                "error": f"HTTP {http_status} body={r.text[:200]}",
            }

        with open(tmp_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 128):
                if chunk:
                    f.write(chunk)

        os.replace(tmp_path, fpath)  # atomic replace
        s256 = sha256_file(fpath)

        time.sleep(cfg.polite_sleep_sec)
        return {
            "format": expected_ext.lstrip("."),
            "file_path": str(fpath),
            "sha256": s256,
            "status": "ok",
            "http_status": http_status,
            "error": "",
        }

    except Exception as e:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        return {
            "format": expected_ext.lstrip("."),
            "file_path": "",
            "sha256": "",
            "status": "failed",
            "http_status": None,
            "error": repr(e),
        }