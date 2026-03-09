# core/download/providers/elsevier.py
from __future__ import annotations

from typing import Any, Dict
from urllib.parse import quote

from core.download.link_fetcher import download_via_url
from core.download.providers.base import ProviderDownloader, DownloadContext


class ElsevierDownloader(ProviderDownloader):
    provider = "elsevier"

    def can_handle(self, doi: str, article: Dict[str, Any]) -> bool:
        return doi.lower().startswith("10.1016/")

    def download(self, doi: str, article: Dict[str, Any], ctx: DownloadContext) -> Dict[str, Any]:
        if not ctx.elsevier_api_key:
            return {
                "provider": self.provider,
                "format": "xml",
                "file_path": "",
                "sha256": "",
                "status": "skipped",
                "http_status": None,
                "error": "missing ELSEVIER_API_KEY",
            }

        doi_enc = quote(doi, safe="")
        out_dir = ctx.base_dir / "data" / "fulltext" / self.provider

        # 认证头
        headers = {
            "X-ELS-APIKey": ctx.elsevier_api_key,
            # 给一个 Accept 作为双保险（url里也带 httpAccept）
            "Accept": "application/xml",
        }
        # 有 insttoken 才带（如果不匹配会 401）
        if getattr(ctx, "elsevier_insttoken", None):
            headers["X-ELS-Insttoken"] = ctx.elsevier_insttoken

        # ✅ XML 优先
        url_xml = f"https://api.elsevier.com/content/article/doi/{doi_enc}?httpAccept=application/xml&view=FULL"
        rec = download_via_url(
            doi,
            url_xml,
            out_dir=out_dir,
            cfg=ctx.cfg,
            session=ctx.session,
            extra_headers=headers,
            expected_ext=".xml",
            file_stem=article.get("title", ""),
        )
        rec["provider"] = self.provider
        return rec