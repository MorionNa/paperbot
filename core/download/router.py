# core/download/router.py
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import requests

from core.download.link_fetcher import DownloadConfig, pick_text_mining_link, download_via_url
from core.download.providers.base import DownloadContext, ProviderDownloader
from core.download.providers import WileyDownloader, SpringerDownloader, ElsevierDownloader, AcmDownloader


@dataclass
class RouterConfig:
    timeout_sec: int = 20
    polite_sleep_sec: float = 0.2
    prefer_xml: bool = True


class DownloadRouter:
    def __init__(self, base_dir: Path, cfg: RouterConfig):
        self.base_dir = base_dir
        self.cfg = cfg
        self.session = requests.Session()

        self.download_cfg = DownloadConfig(
            timeout_sec=cfg.timeout_sec,
            polite_sleep_sec=cfg.polite_sleep_sec,
            prefer_xml=cfg.prefer_xml,
            user_agent="paperbot/0.1 (fulltext)",
        )

        self.ctx = DownloadContext(
            base_dir=base_dir,
            session=self.session,
            cfg=self.download_cfg,
            wiley_token=os.getenv("WILEY_TDM_CLIENT_TOKEN", None),
            springer_api_key=os.getenv("SPRINGER_API_KEY", None),
            elsevier_api_key=os.getenv("ELSEVIER_API_KEY", None),
            elsevier_insttoken=os.getenv("ELSEVIER_INSTTOKEN", None),  # ✅ 新增
            acm_api_key=os.getenv("ACM_API_KEY", None),
            acm_api_url_template=os.getenv("ACM_API_URL_TEMPLATE", None),
        )

        self.providers: List[ProviderDownloader] = [
            WileyDownloader(),
            SpringerDownloader(),
            ElsevierDownloader(),
            AcmDownloader(),
        ]

    @classmethod
    def from_app_config(cls, base_dir: Path, app_cfg: dict) -> "DownloadRouter":
        dl = app_cfg.get("download", {}) or {}
        cfg = RouterConfig(
            timeout_sec=int(dl.get("timeout_sec", 20)),
            polite_sleep_sec=float(dl.get("polite_sleep_sec", 0.2)),
            prefer_xml=True,
        )
        return cls(base_dir, cfg)

    def download(self, article: Dict[str, Any]) -> Dict[str, Any]:
        doi = (article.get("doi") or "").strip()
        if not doi:
            return {
                "provider": "unknown",
                "format": "xml",
                "file_path": "",
                "sha256": "",
                "status": "skipped",
                "http_status": None,
                "error": "missing doi",
            }

        # 1) provider 专用 downloader
        for p in self.providers:
            if p.can_handle(doi, article):
                return p.download(doi, article, self.ctx)

        # 2) 兜底：Crossref text-mining link
        raw = article.get("raw") or {}
        picked = pick_text_mining_link(raw, prefer_xml=True)
        if not picked:
            return {
                "provider": "crossref",
                "format": "xml",
                "file_path": "",
                "sha256": "",
                "status": "skipped",
                "http_status": None,
                "error": "no text-mining link",
            }

        url, _ctype = picked
        out_dir = self.base_dir / "data" / "fulltext" / "crossref"
        rec = download_via_url(
            doi,
            url,
            out_dir=out_dir,
            cfg=self.download_cfg,
            session=self.session,
            extra_headers=None,
            expected_ext=".xml",
        )
        rec["provider"] = "crossref"
        return rec
