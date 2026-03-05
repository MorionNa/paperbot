from __future__ import annotations
import json
from typing import Any, Dict, Optional
import os
from openai import OpenAI
from infra.llm.base import BaseLLM
from infra.llm.types import LLMResult, LLMQuotaError, LLMAuthError, LLMTransientError, is_quota_error


class OpenAILLM(BaseLLM):
    def __init__(self, model: str, base_url: str | None = None, api_key_env: str = "OPENAI_API_KEY"):
        self.model = model
        api_key = os.getenv(api_key_env, "")
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def generate_text(self, *, system: str, user: str, max_output_tokens: int) -> LLMResult:
        try:
            resp = self.client.responses.create(
                model=self.model,
                instructions=system,
                input=user,
                max_output_tokens=max_output_tokens,
            )
            return LLMResult(text=resp.output_text, raw=resp)
        except Exception as e:
            msg = repr(e)
            if is_quota_error(msg):
                raise LLMQuotaError(msg)
            if "401" in msg or "403" in msg:
                raise LLMAuthError(msg)
            raise LLMTransientError(msg)

    def generate_json(self, *, system: str, user: str, schema: Optional[Dict[str, Any]], max_output_tokens: int) -> Dict[str, Any]:
        if not schema:
            # 没 schema 就退化成“强制输出 JSON 字符串再 parse”
            out = self.generate_text(system=system, user=user, max_output_tokens=max_output_tokens).text
            return json.loads(out)

        try:
            resp = self.client.responses.create(
                model=self.model,
                instructions=system,
                input=user,
                max_output_tokens=max_output_tokens,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "paper_summary",
                        "schema": schema,
                        "strict": True,
                    }
                },
            )
            return json.loads(resp.output_text)
        except Exception as e:
            msg = repr(e)
            if is_quota_error(msg):
                raise LLMQuotaError(msg)
            if "401" in msg or "403" in msg:
                raise LLMAuthError(msg)
            raise LLMTransientError(msg)