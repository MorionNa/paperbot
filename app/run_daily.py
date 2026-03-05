# app/run_daily.py
from __future__ import annotations
from datetime import date, timedelta, datetime
from pathlib import Path
import json
import pandas as pd
import os
import yaml
from core.download.router import DownloadRouter
from infra.db import get_fulltext_status, upsert_fulltext
from core.discover.crossref import CrossrefClient, CrossrefConfig, discover_recent_papers_for_journal
from core.export.excel import export_new_articles_to_excel
from infra.db import connect_sqlite, init_db, insert_articles
from core.download.crossref_tdm import DownloadConfig, pick_text_mining_xml_link, download_xml_via_url
from infra.db import get_fulltext_status, upsert_fulltext
import requests
from infra.secrets import load_secrets_into_env

def _load_config(base_dir: Path) -> dict:
    cfg_path = base_dir / "config" / "config.yml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _dated_output_path(base_dir: Path, pipeline_cfg: dict) -> Path:
    """
    If pipeline.output_excel is 'outputs/daily_papers.xlsx',
    output becomes 'outputs/daily_papers_YYYY-MM-DD_HHMMSS.xlsx'
    """
    raw = pipeline_cfg.get("output_excel", "outputs/daily_papers.xlsx")
    p = (base_dir / raw).resolve()

    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    return p.with_name(f"{p.stem}_{ts}{p.suffix}")

def _json_list_to_str(s: str) -> str:
    if not s:
        return ""
    try:
        obj = json.loads(s)
        if isinstance(obj, list):
            return "; ".join(str(x) for x in obj)
        return str(obj)
    except Exception:
        return str(s)


def export_new_articles_with_summaries(conn, new_articles: list[dict], out_path: Path) -> None:
    """
    导出“本次新增论文”的 Excel，并附带数据库里的总结字段（summaries）与全文下载字段（fulltexts）。
    如果某篇还没总结/还没下载，对应列为空即可。
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    dois = [a.get("doi", "").strip() for a in new_articles if a.get("doi")]
    dois = [d for d in dois if d]

    summary_map = {}
    fulltext_map = {}

    if dois:
        placeholders = ",".join(["?"] * len(dois))

        # summaries
        s_rows = conn.execute(
            f"""
            SELECT doi, model, method_summary, result_summary, keywords_json, tags_json, status, error, summarized_at
            FROM summaries
            WHERE doi IN ({placeholders})
            """,
            dois,
        ).fetchall()

        for (doi, model, method_summary, result_summary, keywords_json, tags_json, status, error, summarized_at) in s_rows:
            summary_map[doi] = {
                "summary_model": model or "",
                "method_summary": method_summary or "",
                "result_summary": result_summary or "",
                "keywords": _json_list_to_str(keywords_json or ""),
                "tags": _json_list_to_str(tags_json or ""),
                "summary_status": status or "",
                "summary_error": error or "",
                "summarized_at": summarized_at or "",
            }

        # fulltexts（可选，但建议一起带上，方便你看哪些已下载/路径在哪）
        f_rows = conn.execute(
            f"""
            SELECT doi, provider, format, file_path, status, http_status, error, downloaded_at
            FROM fulltexts
            WHERE doi IN ({placeholders})
            """,
            dois,
        ).fetchall()

        for (doi, provider, fmt, file_path, status, http_status, error, downloaded_at) in f_rows:
            fulltext_map[doi] = {
                "fulltext_provider": provider or "",
                "fulltext_format": fmt or "",
                "fulltext_path": file_path or "",
                "fulltext_status": status or "",
                "fulltext_http": http_status if http_status is not None else "",
                "fulltext_error": error or "",
                "downloaded_at": downloaded_at or "",
            }

    rows = []
    for a in new_articles:
        doi = (a.get("doi") or "").strip()
        s = summary_map.get(doi, {})
        f = fulltext_map.get(doi, {})

        rows.append(
            {
                # 元数据
                "published_date": a.get("published_date", ""),
                "journal": a.get("journal", ""),
                "publisher": a.get("publisher", ""),
                "title": a.get("title", ""),
                "doi": doi,
                "url": a.get("url", ""),
                "authors": "; ".join(a.get("authors") or []),
                "subjects": "; ".join(a.get("subjects") or []),

                # 全文下载状态
                "fulltext_status": f.get("fulltext_status", a.get("fulltext_status", "")),
                "fulltext_provider": f.get("fulltext_provider", ""),
                "fulltext_format": f.get("fulltext_format", ""),
                "fulltext_path": f.get("fulltext_path", a.get("fulltext_path", "")),
                "fulltext_http": f.get("fulltext_http", ""),
                "fulltext_error": f.get("fulltext_error", ""),
                "downloaded_at": f.get("downloaded_at", ""),

                # 总结字段
                "summary_status": s.get("summary_status", ""),
                "summary_model": s.get("summary_model", ""),
                "method_summary": s.get("method_summary", ""),
                "result_summary": s.get("result_summary", ""),
                "keywords": s.get("keywords", ""),
                "tags": s.get("tags", ""),
                "summarized_at": s.get("summarized_at", ""),
                "summary_error": s.get("summary_error", ""),
            }
        )

    df = pd.DataFrame(rows)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="new_papers")

def main():
    base_dir = Path(__file__).resolve().parents[1]  # E:\paperbot
    load_secrets_into_env(base_dir)  # ✅ 加这一行，确保 ELSEVIER_API_KEY 进入 os.environ
    print("ELSEVIER_API_KEY len =", len(os.getenv("ELSEVIER_API_KEY", "")), flush=True)
    cfg = _load_config(base_dir)

    lookback = int(cfg["pipeline"]["lookback_days"])
    until_d = date.today()
    from_d = until_d - timedelta(days=lookback)

    cr_cfg_dict = cfg.get("crossref", {}) or {}
    cr_cfg = CrossrefConfig(
        mailto=cr_cfg_dict.get("mailto"),
        timeout_sec=int(cr_cfg_dict.get("timeout_sec", 30)),
        per_page=int(cr_cfg_dict.get("per_page", 200)),
        polite_sleep_sec=float(cr_cfg_dict.get("polite_sleep_sec", 1.0)),
    )
    client = CrossrefClient(cr_cfg)

    # DB
    conn = connect_sqlite(cfg["pipeline"]["db_url"], base_dir)
    init_db(conn)

    all_new = []
    for j in cfg["journals"]:
        items = discover_recent_papers_for_journal(client, j, from_d, until_d)
        new_items = insert_articles(conn, items)
        print(f"[{j['name']}] fetched={len(items)} inserted(new)={len(new_items)}")
        all_new.extend(new_items)

    # ---- Fulltext download (XML first) ----
    router = DownloadRouter.from_app_config(base_dir, cfg)

    for idx, a in enumerate(all_new, 1):
        doi = a["doi"]
        print(f"[DL {idx}/{len(all_new)}] {doi}", flush=True)

        if get_fulltext_status(conn, doi) == "ok":
            a["fulltext_status"] = "ok"
            a["fulltext_path"] = ""
            print("  -> already ok", flush=True)
            continue

        rec = router.download(a)
        upsert_fulltext(conn, doi, rec)

        a["fulltext_status"] = rec.get("status", "")
        a["fulltext_path"] = rec.get("file_path", "")
        print(f"  -> {a['fulltext_status']} http={rec.get('http_status')} err={rec.get('error')}", flush=True)

    out_path = _dated_output_path(base_dir, cfg["pipeline"])
    export_new_articles_with_summaries(conn, all_new, out_path)

    print(f"Done. New articles: {len(all_new)}")
    print(f"Excel written to: {out_path}")

    conn.close()


if __name__ == "__main__":
    main()