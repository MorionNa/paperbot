# core/download/providers/__init__.py
from core.download.providers.wiley import WileyDownloader
from core.download.providers.springer import SpringerDownloader
from core.download.providers.elsevier import ElsevierDownloader

__all__ = ["WileyDownloader", "SpringerDownloader", "ElsevierDownloader"]