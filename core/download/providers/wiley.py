# core/download/providers/wiley.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from core.download.link_fetcher import pick_text_mining_link, download_via_url
from core.download.providers.base import ProviderDownloader, DownloadContext


class WileyDownloader(ProviderDownloader):
    provider = "wiley"

    def can_handle(self, doi: str, article: Dict[str, Any]) -> bool:
        return doi.lower().startswith("10.1002/")

    def download(self, doi: str, article: Dict[str, Any], ctx: DownloadContext) -> Dict[str, Any]:
        if not ctx.wiley_token:
            return {
                "provider": self.provider,
                "format": "xml",
                "file_path": "",
                "sha256": "",
                "status": "skipped",
                "http_status": None,
                "error": "missing WILEY_TDM_CLIENT_TOKEN",
            }

        raw = article.get("raw") or {}
        picked = pick_text_mining_link(raw, prefer_xml=True)
        if not picked:
            return {
                "provider": self.provider,
                "format": "xml",
                "file_path": "",
                "sha256": "",
                "status": "skipped",
                "http_status": None,
                "error": "no text-mining link",
            }

        url, ctype = picked
        out_dir = ctx.base_dir / "data" / "fulltext" / self.provider

        rec = download_via_url(
            doi,
            url,
            out_dir=out_dir,
            cfg=ctx.cfg,
            session=ctx.session,
            extra_headers={"Wiley-TDM-Client-Token": ctx.wiley_token},
            expected_ext=".xml",
            file_stem=article.get("title", ""),
        )
        rec["provider"] = self.provider
        return rec