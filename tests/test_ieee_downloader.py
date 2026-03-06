import unittest
from pathlib import Path

from core.download.link_fetcher import DownloadConfig
from core.download.providers.ieee import IeeeDownloader
from core.download.providers.base import DownloadContext


class _FakeSession:
    pass


class IeeeDownloaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.downloader = IeeeDownloader()
        self.base_ctx = DownloadContext(
            base_dir=Path('.'),
            session=_FakeSession(),
            cfg=DownloadConfig(),
        )

    def test_can_handle_ieee_doi_prefix(self):
        self.assertTrue(self.downloader.can_handle('10.1109/5.771073', {}))

    def test_can_handle_ieee_publisher_name(self):
        article = {'publisher': 'Institute of Electrical and Electronics Engineers (IEEE)'}
        self.assertTrue(self.downloader.can_handle('10.9999/example', article))

    def test_download_requires_api_key(self):
        rec = self.downloader.download('10.1109/5.771073', {}, self.base_ctx)
        self.assertEqual(rec['status'], 'skipped')
        self.assertIn('IEEE_API_KEY', rec['error'])

    def test_builtin_template_contains_placeholders(self):
        self.assertIn('{doi}', self.downloader.IEEE_API_URL_TEMPLATE)
        self.assertIn('{api_key}', self.downloader.IEEE_API_URL_TEMPLATE)


if __name__ == '__main__':
    unittest.main()
