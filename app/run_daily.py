# app/run_daily.py
from __future__ import annotations

from datetime import date, timedelta, datetime
from pathlib import Path
import json
import pandas as pd
import os
import re
import yaml
import csv
from typing import Dict, List, Optional

from core.download.router import DownloadRouter
from infra.db import get_fulltext_status, upsert_fulltext
from core.discover.crossref import CrossrefClient, CrossrefConfig, discover_recent_papers_for_journal
from infra.db import connect_sqlite, init_db, insert_articles
from infra.secrets import load_secrets_into_env


def _load_config(base_dir: Path) -> dict:
    cfg_path = base_dir / "config" / "config.yml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _dated_output_path(base_dir: Path, pipeline_cfg: dict) -> Path:
    raw = pipeline_cfg.get("output_excel", "outputs/daily_papers.xlsx")
    p = (base_dir / raw).resolve()
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    return p.with_name(f"{p.stem}_{ts}{p.suffix}")




def _parse_iso_date(value: str, field_name: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception as e:
        raise ValueError(f"invalid {field_name}: {value!r}, expected YYYY-MM-DD") from e


def _resolve_date_range(pipeline_cfg: dict) -> tuple[date, date]:
    """
    解析抓取区间：
    1) 若配置了 date_from/date_until，则按指定区间抓取；
    2) 否则回退到 lookback_days（默认行为）。
    """
    date_from_raw = (pipeline_cfg.get("date_from") or "").strip()
    date_until_raw = (pipeline_cfg.get("date_until") or "").strip()

    if date_from_raw and date_until_raw:
        from_d = _parse_iso_date(date_from_raw, "pipeline.date_from")
        until_d = _parse_iso_date(date_until_raw, "pipeline.date_until")
    elif date_from_raw or date_until_raw:
        raise ValueError("pipeline.date_from and pipeline.date_until must be set together")
    else:
        lookback = int(pipeline_cfg.get("lookback_days", 30))
        until_d = date.today()
        from_d = until_d - timedelta(days=lookback)

    if from_d > until_d:
        raise ValueError(f"invalid date range: date_from({from_d}) > date_until({until_d})")

    return from_d, until_d

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
    导出“本次新增论文”的 Excel，并附带 summaries 与 fulltexts 字段。
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

        # fulltexts
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
                "published_date": a.get("published_date", ""),
                "journal": a.get("journal", ""),
                "publisher": a.get("publisher", ""),
                "title": a.get("title", ""),
                "doi": doi,
                "url": a.get("url", ""),
                "authors": "; ".join(a.get("authors") or []),
                "subjects": "; ".join(a.get("subjects") or []),

                "fulltext_status": f.get("fulltext_status", a.get("fulltext_status", "")),
                "fulltext_provider": f.get("fulltext_provider", ""),
                "fulltext_format": f.get("fulltext_format", ""),
                "fulltext_path": f.get("fulltext_path", a.get("fulltext_path", "")),
                "fulltext_http": f.get("fulltext_http", ""),
                "fulltext_error": f.get("fulltext_error", ""),
                "downloaded_at": f.get("downloaded_at", ""),

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


# ------------------------
# Wiley tdm-client helpers
# ------------------------
def _is_wiley_doi(doi: str) -> bool:
    d = (doi or "").lower()
    return d.startswith("10.1002/") or d.startswith("10.1111/")


def _is_springer_doi(doi: str) -> bool:
    d = (doi or "").lower()
    return d.startswith("10.1007/")


def _is_ieee_doi(doi: str, publisher: str = "") -> bool:
    d = (doi or "").lower()
    p = (publisher or "").lower()
    return d.startswith("10.1109/") or ("ieee" in p or "institute of electrical and electronics engineers" in p)


def _sha256_file(p: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_file_stem(text: str, fallback: str, max_len: int = 120) -> str:
    raw = (text or "").strip()
    if not raw:
        return fallback
    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]+', ' ', raw)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip().rstrip('.')
    if not cleaned:
        return fallback
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip()
    return cleaned or fallback


def _rename_wiley_pdf_by_title(pdf_path: Path, title: str, doi: str) -> Path:
    stem = _safe_file_stem(title, fallback=doi.replace('/', '_'))
    target = pdf_path.with_name(stem + ".pdf")
    if target == pdf_path:
        return pdf_path

    if target.exists():
        suffix = doi.split('/')[-1].strip() or "doi"
        suffix = _safe_file_stem(suffix, fallback="doi", max_len=40)
        target = pdf_path.with_name(f"{stem}__{suffix}.pdf")

    os.replace(pdf_path, target)
    return target


def _parse_results_csv(results_csv: Path, run_dir: Path) -> Dict[str, Path]:
    """
    兼容解析 wiley-tdm 输出的 results.csv，提取 doi -> file_path
    """
    mapping: Dict[str, Path] = {}
    if not results_csv.exists():
        return mapping

    with results_csv.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return mapping

        fns = [x.lower() for x in reader.fieldnames]
        doi_key = next((reader.fieldnames[i] for i, n in enumerate(fns) if "doi" in n), None)
        path_key = next((reader.fieldnames[i] for i, n in enumerate(fns) if "path" in n or "file" in n), None)
        status_key = next((reader.fieldnames[i] for i, n in enumerate(fns) if "status" in n), None)

        for row in reader:
            d = (row.get(doi_key) or "").strip() if doi_key else ""
            p = (row.get(path_key) or "").strip() if path_key else ""
            st = (row.get(status_key) or "").strip().lower() if status_key else ""
            if not d or not p:
                continue
            if st and st not in ("ok", "success", "downloaded"):
                continue

            pp = Path(p)
            if not pp.is_absolute():
                pp = (run_dir / pp).resolve()
            if pp.exists():
                mapping[d] = pp

    return mapping


def _try_find_pdf_by_suffix(downloads_dir: Path, doi: str) -> Optional[Path]:
    suffix = doi.split("/")[-1]
    cands = list(downloads_dir.rglob(f"*{suffix}*.pdf"))
    if not cands:
        safe1 = doi.replace("/", "_")
        safe2 = doi.replace("/", "-")
        cands = list(downloads_dir.rglob(f"*{safe1}*.pdf")) + list(downloads_dir.rglob(f"*{safe2}*.pdf"))
    if not cands:
        return None
    cands.sort(key=lambda p: p.stat().st_size, reverse=True)
    return cands[0]


def download_wiley_via_tdm_client(conn, base_dir: Path, cfg: dict, dois: List[str], articles: List[dict]) -> None:
    """
    使用 wiley-tdm 批量下载 Wiley PDF 并写入 fulltexts 表。
    """
    if not dois:
        return

    # wiley-tdm 使用 TDM_API_TOKEN
    tok = (os.getenv("WILEY_TDM_CLIENT_TOKEN", "") or "").strip()
    if tok and not os.getenv("TDM_API_TOKEN"):
        os.environ["TDM_API_TOKEN"] = tok

    if not os.getenv("TDM_API_TOKEN"):
        for doi in dois:
            resolved_path_map[doi] = p

        upsert_fulltext(conn, doi, {
                "provider": "wiley",
                "format": "pdf",
                "file_path": "",
                "sha256": "",
                "status": "skipped",
                "http_status": None,
                "error": "missing WILEY_TDM_CLIENT_TOKEN (and TDM_API_TOKEN)",
                "downloaded_at": datetime.now().isoformat(timespec="seconds"),
            })
        for a in articles:
            if a.get("doi") in set(dois):
                a["fulltext_status"] = "skipped"
                a["fulltext_path"] = ""
        return

    try:
        from wiley_tdm import TDMClient
    except Exception as e:
        for doi in dois:
            upsert_fulltext(conn, doi, {
                "provider": "wiley",
                "format": "pdf",
                "file_path": "",
                "sha256": "",
                "status": "failed",
                "http_status": None,
                "error": f"wiley-tdm not installed/importable: {e!r}",
                "downloaded_at": datetime.now().isoformat(timespec="seconds"),
            })
        return

    dl_cfg = cfg.get("download", {}) or {}
    run_root = dl_cfg.get("wiley_run_dir", "data/wiley_tdm_runs")
    run_dir = (base_dir / run_root / datetime.now().strftime("%Y-%m-%d_%H%M%S")).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    dois_file = run_dir / "dois.txt"
    dois_file.write_text("\n".join(dois), encoding="utf-8")

    old_cwd = os.getcwd()
    try:
        os.chdir(run_dir)
        tdm = TDMClient()
        tdm.download_pdfs(str(dois_file))
        tdm.save_results()
    finally:
        os.chdir(old_cwd)

    downloads_dir = run_dir / "downloads"
    results_csv = run_dir / "results.csv"
    csv_map = _parse_results_csv(results_csv, run_dir)

    ok = 0
    doi_set = set(dois)
    resolved_path_map: Dict[str, Path] = {}

    for doi in dois:
        p = csv_map.get(doi) or _try_find_pdf_by_suffix(downloads_dir, doi)
        if p is None or not p.exists():
            upsert_fulltext(conn, doi, {
                "provider": "wiley",
                "format": "pdf",
                "file_path": "",
                "sha256": "",
                "status": "failed",
                "http_status": None,
                "error": "wiley-tdm: file not found after download",
                "downloaded_at": datetime.now().isoformat(timespec="seconds"),
            })
            continue

        title = next((x.get("title", "") for x in articles if (x.get("doi") or "").strip() == doi), "")
        try:
            p = _rename_wiley_pdf_by_title(p, title=title, doi=doi)
        except Exception:
            # 重命名失败不影响入库
            pass

        resolved_path_map[doi] = p

        upsert_fulltext(conn, doi, {
            "provider": "wiley",
            "format": "pdf",
            "file_path": str(p),
            "sha256": _sha256_file(p),
            "status": "ok",
            "http_status": 200,
            "error": "",
            "downloaded_at": datetime.now().isoformat(timespec="seconds"),
        })
        ok += 1

    # 回写到 all_new 里，方便导出
    for a in articles:
        d = (a.get("doi") or "").strip()
        if d in doi_set:
            p = resolved_path_map.get(d) or csv_map.get(d) or _try_find_pdf_by_suffix(downloads_dir, d)
            if p and Path(p).exists():
                a["fulltext_status"] = "ok"
                a["fulltext_path"] = str(p)
            else:
                a["fulltext_status"] = "failed"
                a["fulltext_path"] = ""

    print(f"[Wiley tdm-client] ok={ok}/{len(dois)} run_dir={run_dir}", flush=True)


def main():
    base_dir = Path(__file__).resolve().parents[1]
    load_secrets_into_env(base_dir)

    print("ELSEVIER_API_KEY len =", len(os.getenv("ELSEVIER_API_KEY", "")), flush=True)
    print("WILEY_TDM_CLIENT_TOKEN len =", len(os.getenv("WILEY_TDM_CLIENT_TOKEN", "")), flush=True)

    cfg = _load_config(base_dir)

    from_d, until_d = _resolve_date_range(cfg["pipeline"])
    print(f"[DATE RANGE] from={from_d} until={until_d}", flush=True)

    cr_cfg_dict = cfg.get("crossref", {}) or {}
    cr_cfg = CrossrefConfig(
        mailto=cr_cfg_dict.get("mailto"),
        timeout_sec=int(cr_cfg_dict.get("timeout_sec", 30)),
        per_page=int(cr_cfg_dict.get("per_page", 200)),
        polite_sleep_sec=float(cr_cfg_dict.get("polite_sleep_sec", 1.0)),
    )
    client = CrossrefClient(cr_cfg)

    conn = connect_sqlite(cfg["pipeline"]["db_url"], base_dir)
    init_db(conn)

    all_new: List[dict] = []
    for j in cfg["journals"]:
        items = discover_recent_papers_for_journal(client, j, from_d, until_d)
        new_items = insert_articles(conn, items)
        print(f"[{j['name']}] fetched={len(items)} inserted(new)={len(new_items)}")
        all_new.extend(new_items)

    # ---- Fulltext download ----
    router = DownloadRouter.from_app_config(base_dir, cfg)

    dl_cfg = cfg.get("download", {}) or {}
    wiley_mode = (dl_cfg.get("wiley_mode") or "tdm_client").lower()
    wiley_limit = int(dl_cfg.get("wiley_limit_per_run", 30))

    wiley_pending: List[str] = []

    for idx, a in enumerate(all_new, 1):
        doi = a["doi"]
        print(f"[DL {idx}/{len(all_new)}] {doi}", flush=True)

        if get_fulltext_status(conn, doi) == "ok":
            a["fulltext_status"] = "ok"
            a["fulltext_path"] = ""
            print("  -> already ok", flush=True)
            continue

        # ✅ Wiley：先收集，循环后用 tdm-client 批量下载
        if wiley_mode == "tdm_client" and _is_wiley_doi(doi):
            wiley_pending.append(doi)
            a["fulltext_status"] = "pending_wiley"
            a["fulltext_path"] = ""
            print("  -> pending (wiley tdm-client)", flush=True)
            continue

        # ✅ Springer：在 run_daily 中显式走专用下载分支（底层由 router 调用 SpringerDownloader）
        if _is_springer_doi(doi):
            rec = router.download(a)
            upsert_fulltext(conn, doi, rec)

            a["fulltext_status"] = rec.get("status", "")
            a["fulltext_path"] = rec.get("file_path", "")
            print(f"  -> springer {a['fulltext_status']} http={rec.get('http_status')} err={rec.get('error')}", flush=True)
            continue

        # ✅ IEEE：在 run_daily 中显式走专用下载分支（底层由 router 调用 IeeeDownloader）
        if _is_ieee_doi(doi, a.get("publisher", "")):
            rec = router.download(a)
            upsert_fulltext(conn, doi, rec)

            a["fulltext_status"] = rec.get("status", "")
            a["fulltext_path"] = rec.get("file_path", "")
            print(f"  -> ieee {a['fulltext_status']} http={rec.get('http_status')} err={rec.get('error')}", flush=True)
            continue

        rec = router.download(a)
        upsert_fulltext(conn, doi, rec)

        a["fulltext_status"] = rec.get("status", "")
        a["fulltext_path"] = rec.get("file_path", "")
        print(f"  -> {a['fulltext_status']} http={rec.get('http_status')} err={rec.get('error')}", flush=True)

    # ✅ Wiley 批量下载（限制每日数量）
    if wiley_pending:
        wiley_pending = wiley_pending[:wiley_limit]
        download_wiley_via_tdm_client(conn, base_dir, cfg, wiley_pending, all_new)

    # 仅保留下载成功的论文到 papers.db（本轮新发现条目）
    successful_new: List[dict] = [a for a in all_new if (a.get("fulltext_status") or "").lower() == "ok"]
    failed_new_dois = [(a.get("doi") or "").strip() for a in all_new if (a.get("fulltext_status") or "").lower() != "ok" and (a.get("doi") or "").strip()]
    if failed_new_dois:
        conn.executemany("DELETE FROM fulltexts WHERE doi = ?;", [(d,) for d in failed_new_dois])
        conn.executemany("DELETE FROM articles WHERE doi = ?;", [(d,) for d in failed_new_dois])
        conn.commit()
        print(f"[DB CLEANUP] removed non-downloaded records: {len(failed_new_dois)}", flush=True)
    all_new = successful_new

    out_path = _dated_output_path(base_dir, cfg["pipeline"])
    export_new_articles_with_summaries(conn, all_new, out_path)

    print(f"Done. New articles: {len(all_new)}")
    print(f"Excel written to: {out_path}")

    conn.close()


if __name__ == "__main__":
    main()
