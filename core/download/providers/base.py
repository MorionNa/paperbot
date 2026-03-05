# core/download/providers/base.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from core.download.link_fetcher import DownloadConfig


@dataclass
class DownloadContext:
    base_dir: Path
    session: requests.Session
    cfg: DownloadConfig
    # 你也可以把 token/key 放这里（从 env 读进来），避免到处 os.getenv
    wiley_token: Optional[str] = None
    springer_api_key: Optional[str] = None
    elsevier_api_key: Optional[str] = None
    elsevier_insttoken: Optional[str] = None


class ProviderDownloader:
    """
    Skeleton interface.
    Return dict fields for fulltexts table:
      provider, format, file_path, sha256, status, http_status, error, downloaded_at
    """
    provider: str = "base"

    def can_handle(self, doi: str, article: Dict[str, Any]) -> bool:
        raise NotImplementedError

    def download(self, doi: str, article: Dict[str, Any], ctx: DownloadContext) -> Dict[str, Any]:
        raise NotImplementedError