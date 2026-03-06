import unittest
from pathlib import Path

from core.download.link_fetcher import DownloadConfig
from core.download.providers.acm import AcmDownloader
from core.download.providers.base import DownloadContext


class _FakeSession:
    pass


class AcmDownloaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.downloader = AcmDownloader()
        self.base_ctx = DownloadContext(
            base_dir=Path('.'),
            session=_FakeSession(),
            cfg=DownloadConfig(),
        )

    def test_can_handle_acm_doi_prefix(self):
        self.assertTrue(self.downloader.can_handle('10.1145/1234567.7654321', {}))

    def test_can_handle_acm_publisher_name(self):
        article = {'publisher': 'Association for Computing Machinery (ACM)'}
        self.assertTrue(self.downloader.can_handle('10.9999/example', article))

    def test_download_requires_api_key(self):
        rec = self.downloader.download('10.1145/1234567', {}, self.base_ctx)
        self.assertEqual(rec['status'], 'skipped')
        self.assertIn('ACM_API_KEY', rec['error'])

    def test_download_requires_template_with_doi_placeholder(self):
        ctx = DownloadContext(
            base_dir=Path('.'),
            session=_FakeSession(),
            cfg=DownloadConfig(),
            acm_api_key='test-key',
            acm_api_url_template='https://api.acm.org/article',
        )

        rec = self.downloader.download('10.1145/1234567', {}, ctx)
        self.assertEqual(rec['status'], 'skipped')
        self.assertIn('ACM_API_URL_TEMPLATE', rec['error'])


if __name__ == '__main__':
    unittest.main()
