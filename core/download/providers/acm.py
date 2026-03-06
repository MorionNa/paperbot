from __future__ import annotations

from typing import Any, Dict
from urllib.parse import quote

from core.download.link_fetcher import download_via_url
from core.download.providers.base import ProviderDownloader, DownloadContext


class AcmDownloader(ProviderDownloader):
    provider = "acm"

    def can_handle(self, doi: str, article: Dict[str, Any]) -> bool:
        d = (doi or "").lower()
        if d.startswith("10.1145/"):
            return True

        publisher = (article.get("publisher") or "").lower()
        return "association for computing machinery" in publisher or publisher == "acm"

    def download(self, doi: str, article: Dict[str, Any], ctx: DownloadContext) -> Dict[str, Any]:
        if not ctx.acm_api_key:
            return {
                "provider": self.provider,
                "format": "xml",
                "file_path": "",
                "sha256": "",
                "status": "skipped",
                "http_status": None,
                "error": "missing ACM_API_KEY",
            }

        url_template = ctx.acm_api_url_template or ""
        if "{doi}" not in url_template:
            return {
                "provider": self.provider,
                "format": "xml",
                "file_path": "",
                "sha256": "",
                "status": "skipped",
                "http_status": None,
                "error": "missing/invalid ACM_API_URL_TEMPLATE (must contain {doi})",
            }

        doi_enc = quote(doi, safe="")
        url = url_template.format(doi=doi_enc)
        out_dir = ctx.base_dir / "data" / "fulltext" / self.provider

        headers = {
            "Authorization": f"Bearer {ctx.acm_api_key}",
            "X-ACM-API-Key": ctx.acm_api_key,
            "Accept": "application/xml,text/xml;q=0.9,*/*;q=0.8",
        }

        rec = download_via_url(
            doi,
            url,
            out_dir=out_dir,
            cfg=ctx.cfg,
            session=ctx.session,
            extra_headers=headers,
            expected_ext=".xml",
        )
        rec["provider"] = self.provider
        rec["format"] = "xml"
        return rec
