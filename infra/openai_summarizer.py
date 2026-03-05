# infra/openai_summarizer.py
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List

from openai import OpenAI


SUMMARY_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "method_summary": {"type": "string"},
        "result_summary": {"type": "string"},
        "keywords": {"type": "array", "items": {"type": "string"}},
        "tags": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "string"},
    },
    "required": ["method_summary", "result_summary", "keywords", "tags", "notes"],
}


def _retry_sleep(attempt: int) -> float:
    # 1s, 2s, 4s, 8s...
    return min(30.0, 2.0 ** attempt)


class PaperSummarizer:
    def __init__(self, model: str = "gpt-5.2"):
        self.model = model
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    def summarize(
        self,
        *,
        title: str,
        abstract: str,
        chunk_summaries: List[str],
        language: str = "zh",
        max_output_tokens: int = 900,
    ) -> Dict[str, Any]:
        """
        Map-reduce: 你先把正文分块，每块做 chunk summary，然后把 chunk summaries 合并为最终结构化总结。
        这里的输入只包含：title/abstract + chunk_summaries（更省 token、更稳）。
        """
        joined = "\n\n".join(f"- {s}" for s in chunk_summaries if s.strip())

        instructions = (
            "你是土木/结构工程方向的科研助理。"
            "请基于给定论文信息与分块摘要，输出结构化总结。"
            "用中文输出，必要的专业术语保留英文缩写（如 PINN/GNN）。"
            "method_summary/result_summary 要具体，不要泛泛而谈；如果没有数值就不要编造。"
        )

        user_input = (
            f"Title: {title}\n"
            f"Abstract: {abstract}\n\n"
            f"Chunk summaries:\n{joined}\n\n"
            "请按照 JSON Schema 输出：\n"
            "- method_summary: 方法/流程/模型要点（2-6句）\n"
            "- result_summary: 主要结论/效果/对比（2-6句）\n"
            "- keywords: 5-12个关键词\n"
            "- tags: 3-10个主题标签（可用于检索，如 'PINN','Seismic','Surrogate','Uncertainty'）\n"
            "- notes: 任何不确定/缺失信息说明\n"
        )

        for attempt in range(6):
            try:
                resp = self.client.responses.create(
                    model=self.model,
                    instructions=instructions,
                    input=user_input,
                    max_output_tokens=max_output_tokens,
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": "paper_summary",
                            "schema": SUMMARY_SCHEMA,
                            "strict": True,
                        }
                    },
                )
                # Structured Outputs：output_text 就是 JSON 字符串
                data = json.loads(resp.output_text)
                return data
            except Exception as e:
                if attempt == 5:
                    raise
                time.sleep(_retry_sleep(attempt))