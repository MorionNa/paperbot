# core/download/providers/springer.py
from __future__ import annotations

from typing import Any, Dict

from core.download.link_fetcher import pick_text_mining_link, download_via_url
from core.download.providers.base import ProviderDownloader, DownloadContext


class SpringerDownloader(ProviderDownloader):
    provider = "springer"

    def can_handle(self, doi: str, article: Dict[str, Any]) -> bool:
        return doi.lower().startswith("10.1007/")

    def download(self, doi: str, article: Dict[str, Any], ctx: DownloadContext) -> Dict[str, Any]:
        # MVP：先尝试 Crossref text-mining link（有的 OA 能直接下）
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
                "error": "no text-mining link (springer api not implemented yet)",
            }

        url, ctype = picked
        out_dir = ctx.base_dir / "data" / "fulltext" / self.provider

        rec = download_via_url(
            doi,
            url,
            out_dir=out_dir,
            cfg=ctx.cfg,
            session=ctx.session,
            extra_headers=None,
            expected_ext=".pdf",  # ← Springer 当前实际返回 PDF
        )
        rec["provider"] = self.provider
        rec["format"] = "pdf"  # 可显式写一下（可选）
        return rec