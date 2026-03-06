from __future__ import annotations

from typing import Any, Dict
from urllib.parse import quote

from core.download.link_fetcher import download_via_url
from core.download.providers.base import ProviderDownloader, DownloadContext


class IeeeDownloader(ProviderDownloader):
    provider = "ieee"
    IEEE_API_URL_TEMPLATE = (
        "https://ieeexploreapi.ieee.org/api/v1/search/articles?doi={doi}&apikey={api_key}&format=xml"
    )

    def can_handle(self, doi: str, article: Dict[str, Any]) -> bool:
        d = (doi or "").lower()
        if d.startswith("10.1109/"):
            return True

        publisher = (article.get("publisher") or "").lower()
        return "ieee" in publisher or "institute of electrical and electronics engineers" in publisher

    def download(self, doi: str, article: Dict[str, Any], ctx: DownloadContext) -> Dict[str, Any]:
        if not ctx.ieee_api_key:
            return {
                "provider": self.provider,
                "format": "xml",
                "file_path": "",
                "sha256": "",
                "status": "skipped",
                "http_status": None,
                "error": "missing IEEE_API_KEY",
            }

        doi_enc = quote(doi, safe="")
        api_key_enc = quote(ctx.ieee_api_key, safe="")
        url = self.IEEE_API_URL_TEMPLATE.format(doi=doi_enc, api_key=api_key_enc)
        out_dir = ctx.base_dir / "data" / "fulltext" / self.provider

        rec = download_via_url(
            doi,
            url,
            out_dir=out_dir,
            cfg=ctx.cfg,
            session=ctx.session,
            extra_headers={"Accept": "application/xml,text/xml;q=0.9,*/*;q=0.8"},
            expected_ext=".xml",
        )
        rec["provider"] = self.provider
        rec["format"] = "xml"
        return rec
