# app/summarize_papers.py
from __future__ import annotations
import os
import json
import sqlite3
from datetime import datetime

from infra.db import connect_sqlite, init_db
from core.summarize.chunking import chunk_text
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
    base_dir = Path(__file__).resolve().parents[1]
    load_secrets_into_env(base_dir)
    cfg = yaml.safe_load((base_dir / "config" / "config.yml").read_text(encoding="utf-8"))
    conn = connect_sqlite(cfg["pipeline"]["db_url"], base_dir)
    init_db(conn)

    # ------- 通用 LLM client -------
    print("llm.base_url =", cfg["llm"].get("base_url"))
    print("DASHSCOPE_API_KEY len =", len(os.getenv("DASHSCOPE_API_KEY", "")))
    llm = make_llm(cfg)

    limit = int(cfg["summarize"]["limit_per_run"])
    max_chars = int(cfg["summarize"]["chunk_max_chars"])
    max_chunks = int(cfg["summarize"]["max_chunks"])
    max_output_tokens = int(cfg["llm"]["max_output_tokens"])
    stop_on_quota = bool(cfg["llm"].get("stop_on_quota", True))

    rows = fetch_unsummarized(conn, limit=limit)
    print(f"to_summarize: {len(rows)}")

    system_chunk = (
        "你是结构工程科研助理。请阅读论文正文的一个片段，输出该片段的摘要（100-200字），"
        "重点提炼：方法要点、实验/结果线索、关键术语。用中文输出。"
    )
    system_final = (
        "你是结构工程科研助理。请基于论文信息与分块摘要，输出结构化总结。"
        "用中文输出，必要的专业术语保留英文缩写（如 PINN/GNN）。"
        "不要编造不存在的数值或结论。"
    )

    for i, (doi, title, abstract, body_text, journal) in enumerate(rows, 1):
        print(f"[{i}/{len(rows)}] {doi} ({journal})", flush=True)

        try:
            chunks = chunk_text(body_text, max_chars=max_chars, overlap=300)[:max_chunks]
            if not chunks:
                raise RuntimeError("empty chunks")

            # A) chunk summaries（通用接口）
            c_summaries = []
            for k, ch in enumerate(chunks, 1):
                s = llm.generate_text(
                    system=system_chunk,
                    user=f"Title: {title}\nChunk {k}/{len(chunks)}:\n{ch}",
                    max_output_tokens=300,
                ).text.strip()
                c_summaries.append(s)

            # B) final structured summary（你问的这段就放在这里）
            user_prompt = (
                f"Title: {title or ''}\n"
                f"Abstract: {abstract or ''}\n\n"
                "Chunk summaries:\n" + "\n".join(f"- {x}" for x in c_summaries if x.strip()) + "\n\n"
                "请按 JSON Schema 输出：method_summary / result_summary / keywords / tags / notes。"
            )

            data = llm.generate_json(
                system=system_final,
                user=user_prompt,
                schema=SUMMARY_SCHEMA,
                max_output_tokens=max_output_tokens,
            )

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

    conn.close()
    print("Done.")

if __name__ == "__main__":
    main()