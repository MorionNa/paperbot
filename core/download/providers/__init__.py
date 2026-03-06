# core/download/providers/__init__.py
from core.download.providers.wiley import WileyDownloader
from core.download.providers.springer import SpringerDownloader
from core.download.providers.elsevier import ElsevierDownloader
from core.download.providers.acm import AcmDownloader

__all__ = ["WileyDownloader", "SpringerDownloader", "ElsevierDownloader", "AcmDownloader"]
