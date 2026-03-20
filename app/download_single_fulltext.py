from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import yaml

from core.download.router import DownloadRouter
from infra.db import connect_sqlite, init_db, upsert_fulltext
from infra.secrets import load_secrets_into_env
from app.run_daily import _is_wiley_doi, download_wiley_via_tdm_client


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--doi", required=True)
    return parser.parse_args()


def _load_config(base_dir: Path) -> dict:
    cfg_path = base_dir / "config" / "config.yml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_article(conn, doi: str) -> dict | None:
    row = conn.execute(
        """
        SELECT doi, title, journal, publisher, published_date, url,
               authors_json, subjects_json, type, issn_json, raw_json
        FROM articles
        WHERE doi = ?;
        """,
        (doi,),
    ).fetchone()
    if not row:
        return None

    return {
        "doi": row[0] or "",
        "title": row[1] or "",
        "journal": row[2] or "",
        "publisher": row[3] or "",
        "published_date": row[4] or "",
        "url": row[5] or "",
        "authors": json.loads(row[6] or "[]"),
        "subjects": json.loads(row[7] or "[]"),
        "type": row[8] or "",
        "issn": json.loads(row[9] or "[]"),
        "raw": json.loads(row[10] or "{}"),
    }


def _load_fulltext_status(conn, doi: str) -> str:
    row = conn.execute("SELECT status FROM fulltexts WHERE doi = ?;", (doi,)).fetchone()
    return str(row[0] or "") if row else ""


def main() -> None:
    args = _parse_args()
    doi = args.doi.strip()
    if not doi:
        raise ValueError("missing doi")

    base_dir = Path(__file__).resolve().parents[1]
    load_secrets_into_env(base_dir)
    cfg = _load_config(base_dir)

    conn = connect_sqlite(cfg["pipeline"]["db_url"], base_dir)
    init_db(conn)
    try:
        article = _load_article(conn, doi)
        if not article:
            raise ValueError(f"doi not found in articles: {doi}")

        if _is_wiley_doi(doi) and (cfg.get("download", {}) or {}).get("wiley_mode", "tdm_client").lower() == "tdm_client":
            download_wiley_via_tdm_client(conn, base_dir, cfg, [doi], [article])
            status = _load_fulltext_status(conn, doi)
            print(f"[SINGLE DOWNLOAD] doi={doi} status={status} via=wiley_tdm_client", flush=True)
            if status.lower() != "ok":
                raise RuntimeError(f"download failed for {doi}")
            return

        router = DownloadRouter.from_app_config(base_dir, cfg)
        rec = router.download(article)
        upsert_fulltext(conn, doi, rec)

        status = str(rec.get("status", ""))
        print(f"[SINGLE DOWNLOAD] doi={doi} status={status} http={rec.get('http_status')} error={rec.get('error', '')}", flush=True)
        if status.lower() != "ok":
            raise RuntimeError(rec.get("error") or f"download failed for {doi}")
    except Exception as e:
        upsert_fulltext(
            conn,
            doi,
            {
                "provider": "manual_retry",
                "format": "",
                "file_path": "",
                "sha256": "",
                "status": "failed",
                "http_status": None,
                "error": str(e),
                "downloaded_at": datetime.now().isoformat(timespec="seconds"),
            },
        )
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
