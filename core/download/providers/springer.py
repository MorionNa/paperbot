# core/download/providers/springer.py
from __future__ import annotations
from typing import Any, Dict
from pathlib import Path
from urllib.parse import quote_plus

from core.download.link_fetcher import download_via_url
from core.download.providers.base import ProviderDownloader, DownloadContext


class SpringerDownloader(ProviderDownloader):
    """
    集成 MVP + TDM XML 的 Springer 下载器：
    1) 如果 SPRINGER_API_KEY 可用，优先 TDM JATS XML（正文）
    2) 否则 fallback 原来的 PDF 下载逻辑（MVP）
    """

    provider = "springer"

    def can_handle(self, doi: str, article: Dict[str, Any]) -> bool:
        return doi.lower().startswith("10.1007/")

    def download(self, doi: str, article: Dict[str, Any], ctx: DownloadContext) -> Dict[str, Any]:
        # 先尝试 TDM
        tdm_api_key = getattr(ctx, "springer_api_key", None)
        if tdm_api_key:
            rec = self._download_tdm_xml(doi, ctx, tdm_api_key)
            if rec.get("status") == "ok":
                return rec
            # 如果失败，fall back 到 PDF

        # 原 MVP PDF 下载逻辑
        return self._download_mvp_pdf(doi, article, ctx)

    def _download_tdm_xml(self, doi: str, ctx: DownloadContext, api_key: str) -> Dict[str, Any]:
        """
        Springer TDM JATS XML 下载
        """
        try:
            q = quote_plus(f"doi:{doi}")
            key = quote_plus(api_key)
            url = f"https://spdi.public.springernature.app/xmldata/jats?q={q}&api_key={key}"

            out_dir = ctx.base_dir / "data" / "fulltext" / "springer_tdm"
            rec = download_via_url(
                doi,
                url,
                out_dir=out_dir,
                cfg=ctx.cfg,
                session=ctx.session,
                extra_headers={"Accept": "application/xml"},
                expected_ext=".xml",
            )
            rec["provider"] = "springer_tdm"
            rec["format"] = "xml"
            return rec

        except Exception as e:
            return {
                "provider": "springer_tdm",
                "format": "xml",
                "file_path": "",
                "status": "failed",
                "http_status": None,
                "error": f"TDM download failed: {e!r}",
            }

    def _download_mvp_pdf(self, doi: str, article: Dict[str, Any], ctx: DownloadContext) -> Dict[str, Any]:
        """
        原 MVP PDF 下载逻辑（保持你之前的实现）
        """
        try:
            # 这里示例：尝试 article["links"]["pdf"] 或 text-mining link
            # fallback: 没有链接就返回 skipped
            pdf_url = article.get("links", {}).get("pdf")
            if not pdf_url:
                return {
                    "provider": self.provider,
                    "format": "pdf",
                    "file_path": "",
                    "status": "skipped",
                    "http_status": None,
                    "error": "no PDF link available",
                }

            out_dir = ctx.base_dir / "data" / "fulltext" / self.provider
            rec = download_via_url(
                doi,
                pdf_url,
                out_dir=out_dir,
                cfg=ctx.cfg,
                session=ctx.session,
                extra_headers={"Accept": "application/pdf"},
                expected_ext=".pdf",
            )
            rec["provider"] = self.provider
            rec["format"] = "pdf"
            return rec

        except Exception as e:
            return {
                "provider": self.provider,
                "format": "pdf",
                "file_path": "",
                "status": "failed",
                "http_status": None,
                "error": f"MVP PDF download failed: {e!r}",
            }