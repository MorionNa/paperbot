import unittest

from app.run_daily import _select_journals


class RunDailyJournalSelectionTests(unittest.TestCase):
    def test_select_journals_returns_all_when_no_indexes(self):
        journals = [{"name": "A"}, {"name": "B"}]
        self.assertEqual(journals, _select_journals(journals, ""))

    def test_select_journals_filters_by_indexes(self):
        journals = [{"name": "A"}, {"name": "B"}, {"name": "C"}]
        self.assertEqual([journals[0], journals[2]], _select_journals(journals, "0,2"))

    def test_select_journals_rejects_out_of_range(self):
        journals = [{"name": "A"}]
        with self.assertRaises(ValueError):
            _select_journals(journals, "1")


if __name__ == "__main__":
    unittest.main()
