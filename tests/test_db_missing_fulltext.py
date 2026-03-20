import tempfile
import unittest
from pathlib import Path

from infra.db import (
    connect_sqlite,
    delete_papers_by_dois,
    get_fulltext_status,
    init_db,
    insert_articles,
    list_articles_missing_fulltext,
    list_fulltexts_ok,
    resolve_fulltext_status,
    upsert_fulltext,
)


class ListArticlesMissingFulltextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.tmpdir.name)
        self.conn = connect_sqlite("sqlite:///data/papers.db", self.base_dir)
        init_db(self.conn)

    def tearDown(self) -> None:
        self.conn.close()
        self.tmpdir.cleanup()

    def test_returns_articles_without_fulltext_row(self):
        insert_articles(
            self.conn,
            [{"doi": "10.1000/no-fulltext", "title": "Missing", "authors": [], "subjects": [], "issn": [], "raw": {}}],
        )

        rows = list_articles_missing_fulltext(self.conn)
        self.assertEqual(1, len(rows))
        self.assertEqual("10.1000/no-fulltext", rows[0]["doi"])

    def test_excludes_articles_with_ok_fulltext_and_path(self):
        insert_articles(
            self.conn,
            [{"doi": "10.1000/ok", "title": "Downloaded", "authors": [], "subjects": [], "issn": [], "raw": {}}],
        )
        upsert_fulltext(
            self.conn,
            "10.1000/ok",
            {
                "provider": "x",
                "format": "xml",
                "file_path": "data/fulltext/x.xml",
                "sha256": "abc",
                "status": "ok",
                "http_status": 200,
                "error": "",
            },
        )

        rows = list_articles_missing_fulltext(self.conn)
        self.assertEqual([], rows)

    def test_includes_articles_with_empty_path_even_if_status_ok(self):
        insert_articles(
            self.conn,
            [{"doi": "10.1000/empty-path", "title": "Broken", "authors": [], "subjects": [], "issn": [], "raw": {}}],
        )
        upsert_fulltext(
            self.conn,
            "10.1000/empty-path",
            {
                "provider": "x",
                "format": "xml",
                "file_path": "",
                "sha256": "",
                "status": "ok",
                "http_status": 200,
                "error": "",
            },
        )

        rows = list_articles_missing_fulltext(self.conn)
        self.assertEqual(1, len(rows))
        self.assertEqual("10.1000/empty-path", rows[0]["doi"])

    def test_status_ok_becomes_missing_file_when_local_file_missing(self):
        insert_articles(
            self.conn,
            [{"doi": "10.1000/missing-local", "title": "Broken", "authors": [], "subjects": [], "issn": [], "raw": {}}],
        )
        upsert_fulltext(
            self.conn,
            "10.1000/missing-local",
            {
                "provider": "x",
                "format": "xml",
                "file_path": str(self.base_dir / "not-found.xml"),
                "sha256": "",
                "status": "ok",
                "http_status": 200,
                "error": "",
            },
        )

        self.assertEqual("missing_file", get_fulltext_status(self.conn, "10.1000/missing-local"))
        self.assertEqual([], list_fulltexts_ok(self.conn))

    def test_resolve_fulltext_status_keeps_ok_when_file_exists(self):
        p = self.base_dir / "exists.xml"
        p.write_text("x", encoding="utf-8")
        self.assertEqual("ok", resolve_fulltext_status("ok", str(p)))

    def test_delete_papers_by_dois_removes_related_rows_and_returns_paths(self):
        insert_articles(
            self.conn,
            [{"doi": "10.1000/delete-me", "title": "Delete", "authors": [], "subjects": [], "issn": [], "raw": {}}],
        )
        upsert_fulltext(
            self.conn,
            "10.1000/delete-me",
            {
                "provider": "x",
                "format": "xml",
                "file_path": str(self.base_dir / "delete.xml"),
                "sha256": "",
                "status": "failed",
                "http_status": None,
                "error": "",
            },
        )
        self.conn.execute(
            "INSERT INTO parsed_texts (doi, title, abstract, body_text, parser_version) VALUES (?, ?, ?, ?, ?)",
            ("10.1000/delete-me", "t", "a", "b", "v1"),
        )
        self.conn.execute(
            "INSERT INTO summaries (doi, model, method_summary, result_summary, keywords_json, tags_json, summary_json, status, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("10.1000/delete-me", "m", "", "", "[]", "[]", "{}", "ok", ""),
        )
        self.conn.commit()

        paths = delete_papers_by_dois(self.conn, ["10.1000/delete-me"])
        self.assertEqual([str(self.base_dir / "delete.xml")], paths)
        self.assertIsNone(self.conn.execute("SELECT doi FROM articles WHERE doi = ?", ("10.1000/delete-me",)).fetchone())
        self.assertIsNone(self.conn.execute("SELECT doi FROM fulltexts WHERE doi = ?", ("10.1000/delete-me",)).fetchone())
        self.assertIsNone(self.conn.execute("SELECT doi FROM parsed_texts WHERE doi = ?", ("10.1000/delete-me",)).fetchone())
        self.assertIsNone(self.conn.execute("SELECT doi FROM summaries WHERE doi = ?", ("10.1000/delete-me",)).fetchone())


if __name__ == "__main__":
    unittest.main()
