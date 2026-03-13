# app/summarize_papers.py
from __future__ import annotations
import argparse
import os
import json
import sqlite3
from datetime import datetime

from infra.db import connect_sqlite, init_db
from core.summarize.schema import SUMMARY_SCHEMA
from infra.llm.types import LLMQuotaError

from pathlib import Path
import yaml

from infra.secrets import load_secrets_into_env
from infra.llm.factory import make_llm

def fetch_unsummarized(conn: sqlite3.Connection, limit: int = 20):
    return conn.execute(
        """
        SELECT p.doi, p.title, p.abstract, p.body_text, a.journal
        FROM parsed_texts p
        LEFT JOIN summaries s ON s.doi = p.doi
        LEFT JOIN articles a ON a.doi = p.doi
        WHERE (s.doi IS NULL OR s.status != 'ok')
          AND p.body_text IS NOT NULL AND length(p.body_text) > 1000
        ORDER BY p.parsed_at DESC
        LIMIT ?;
        """,
        (limit,),
    ).fetchall()


def fetch_unsummarized_by_dois(conn: sqlite3.Connection, dois: list[str], limit: int = 200):
    if not dois:
        return []
    placeholders = ",".join(["?"] * len(dois))
    return conn.execute(
        f"""
        SELECT p.doi, p.title, p.abstract, p.body_text, a.journal
        FROM parsed_texts p
        LEFT JOIN summaries s ON s.doi = p.doi
        LEFT JOIN articles a ON a.doi = p.doi
        WHERE p.doi IN ({placeholders})
          AND (s.doi IS NULL OR s.status != 'ok')
          AND p.body_text IS NOT NULL AND length(p.body_text) > 1000
        ORDER BY p.parsed_at DESC
        LIMIT ?;
        """,
        (*dois, limit),
    ).fetchall()




def diagnose_selected_doi(conn: sqlite3.Connection, doi: str) -> str:
    parsed = conn.execute(
        "SELECT length(COALESCE(body_text, '')) FROM parsed_texts WHERE doi = ? LIMIT 1;",
        (doi,),
    ).fetchone()
    summary = conn.execute(
        "SELECT status FROM summaries WHERE doi = ? LIMIT 1;",
        (doi,),
    ).fetchone()

    if summary and str(summary[0] or "").strip().lower() == "ok":
        return "already summarized (status=ok)"
    if not parsed:
        return "no parsed_texts row for this DOI (请先完成解析)"
    body_len = int(parsed[0] or 0)
    if body_len <= 1000:
        return f"body_text too short ({body_len} chars <= 1000)"
    if summary:
        return f"existing summary status={summary[0]}"
    return "not selected by query (unknown filter mismatch)"

def upsert_summary(conn: sqlite3.Connection, doi: str, rec: dict):
    conn.execute(
        """
        INSERT INTO summaries
        (doi, model, method_summary, result_summary, keywords_json, tags_json, summary_json, status, error, summarized_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(doi) DO UPDATE SET
          model=excluded.model,
          method_summary=excluded.method_summary,
          result_summary=excluded.result_summary,
          keywords_json=excluded.keywords_json,
          tags_json=excluded.tags_json,
          summary_json=excluded.summary_json,
          status=excluded.status,
          error=excluded.error,
          summarized_at=excluded.summarized_at;
        """,
        (
            doi,
            rec.get("model", ""),
            rec.get("method_summary", ""),
            rec.get("result_summary", ""),
            rec.get("keywords_json", "[]"),
            rec.get("tags_json", "[]"),
            rec.get("summary_json", "{}"),
            rec.get("status", ""),
            rec.get("error", ""),
            rec.get("summarized_at", datetime.now().isoformat(timespec="seconds")),
        ),
    )
    conn.commit()

def main():
    parser = argparse.ArgumentParser(description="Summarize parsed papers")
    parser.add_argument("--dois", type=str, default="", help="Comma-separated DOI list. If set, summarize only these DOIs.")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parents[1]
    print("[summarize] stage=load_secrets start")
    load_secrets_into_env(base_dir)
    print("[summarize] stage=load_secrets done")
    print("[summarize] stage=load_config start")
    cfg = yaml.safe_load((base_dir / "config" / "config.yml").read_text(encoding="utf-8"))
    print("[summarize] stage=load_config done")
    print("[summarize] stage=db_connect start")
    conn = connect_sqlite(cfg["pipeline"]["db_url"], base_dir)
    init_db(conn)
    print("[summarize] stage=db_connect done")

    # ------- 通用 LLM client -------
    print("llm.base_url =", cfg["llm"].get("base_url"))
    api_key_env = cfg["llm"].get("api_key_env", "OPENAI_API_KEY")
    print(f"{api_key_env} len =", len(os.getenv(api_key_env, "")))
    print("[summarize] stage=make_llm start")
    llm = make_llm(cfg)
    print("[summarize] stage=make_llm done")

    limit = int(cfg["summarize"]["limit_per_run"])
    max_output_tokens = int(cfg["llm"]["max_output_tokens"])
    stop_on_quota = bool(cfg["llm"].get("stop_on_quota", True))

    selected_dois = [x.strip() for x in (args.dois or "").split(",") if x.strip()]
    print(f"[summarize] selected_dois={selected_dois}")
    print("[summarize] stage=fetch_candidates start")
    if selected_dois:
        rows = fetch_unsummarized_by_dois(conn, selected_dois, limit=max(limit, len(selected_dois)))
    else:
        rows = fetch_unsummarized(conn, limit=limit)
    print("[summarize] stage=fetch_candidates done")
    print(f"to_summarize: {len(rows)}")

    if selected_dois:
        candidate_set = {str(r[0] or "").strip() for r in rows}
        missing_dois = [d for d in selected_dois if d not in candidate_set]
        if missing_dois:
            print(f"[summarize] skipped_dois={missing_dois}")
        for d in missing_dois:
            reason = diagnose_selected_doi(conn, d)
            print(f"[summarize] skipped {d}: {reason}")
            upsert_summary(
                conn,
                d,
                {
                    "model": cfg["llm"]["model"],
                    "method_summary": "",
                    "result_summary": "",
                    "keywords_json": "[]",
                    "tags_json": "[]",
                    "summary_json": "{}",
                    "status": "failed",
                    "error": reason,
                },
            )

    system_final = (
        "你是结构工程科研助理。请基于论文标题、摘要与全文，输出结构化总结。"
        "用中文输出，必要的专业术语保留英文缩写（如 PINN/GNN）。"
        "不要编造不存在的数值或结论。"
    )

    for i, (doi, title, abstract, body_text, journal) in enumerate(rows, 1):
        print(f"[{i}/{len(rows)}] {doi} ({journal})", flush=True)

        try:
            body = (body_text or "").strip()
            if not body:
                raise RuntimeError("empty body_text")

            user_prompt = (
                f"Title: {title or ''}\n"
                f"Abstract: {abstract or ''}\n\n"
                f"Full text:\n{body}\n\n"
                "请按 JSON Schema 输出：method_summary / result_summary / keywords / tags / notes。"
            )

            print("  -> full-text json summarize start")
            data = llm.generate_json(
                system=system_final,
                user=user_prompt,
                schema=SUMMARY_SCHEMA,
                max_output_tokens=max_output_tokens,
            )

            print("  -> full-text json summarize done")
            rec = {
                "model": cfg["llm"]["model"],
                "method_summary": data.get("method_summary", ""),
                "result_summary": data.get("result_summary", ""),
                "keywords_json": json.dumps(data.get("keywords", []), ensure_ascii=False),
                "tags_json": json.dumps(data.get("tags", []), ensure_ascii=False),
                "summary_json": json.dumps(data, ensure_ascii=False),
                "status": "ok",
                "error": "",
            }
            upsert_summary(conn, doi, rec)
            print("  -> ok", flush=True)

        except LLMQuotaError as e:
            # 免费额度/限速到了：今天就停，明天继续
            print(f"  -> quota/rate limit hit: {e!r}", flush=True)
            if stop_on_quota:
                break
            raise

        except Exception as e:
            upsert_summary(
                conn,
                doi,
                {
                    "model": cfg["llm"]["model"],
                    "method_summary": "",
                    "result_summary": "",
                    "keywords_json": "[]",
                    "tags_json": "[]",
                    "summary_json": "{}",
                    "status": "failed",
                    "error": repr(e),
                },
            )
            print(f"  -> failed: {e!r}", flush=True)

    print("[summarize] stage=db_close")
    conn.close()
    print("Done.")

if __name__ == "__main__":
    main()
