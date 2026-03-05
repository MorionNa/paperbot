from __future__ import annotations
import json
from typing import Any, Dict, Optional

from google import genai
from google.genai import types

from infra.llm.base import BaseLLM
from infra.llm.types import LLMResult, LLMQuotaError, LLMAuthError, LLMTransientError, is_quota_error


class GeminiLLM(BaseLLM):
    def __init__(self, model: str):
        self.model = model
        self.client = genai.Client()  # uses GEMINI_API_KEY :contentReference[oaicite:9]{index=9}

    def generate_text(self, *, system: str, user: str, max_output_tokens: int) -> LLMResult:
        try:
            resp = self.client.models.generate_content(
                model=self.model,
                contents=f"{system}\n\n{user}",
                config=types.GenerateContentConfig(
                    max_output_tokens=max_output_tokens,
                ),
            )
            return LLMResult(text=(resp.text or ""), raw=resp)
        except Exception as e:
            msg = repr(e)
            if is_quota_error(msg):
                raise LLMQuotaError(msg)
            if "401" in msg or "403" in msg:
                raise LLMAuthError(msg)
            raise LLMTransientError(msg)

    def generate_json(self, *, system: str, user: str, schema: Optional[Dict[str, Any]], max_output_tokens: int) -> Dict[str, Any]:
        # Gemini JSON Mode：response_mime_type="application/json"（schema 可选）:contentReference[oaicite:10]{index=10}
        prompt = (
            f"{system}\n\n{user}\n\n"
            "请只输出 JSON，不要输出任何额外文字。"
        )
        try:
            cfg = types.GenerateContentConfig(
                max_output_tokens=max_output_tokens,
                response_mime_type="application/json",
            )
            resp = self.client.models.generate_content(model=self.model, contents=prompt, config=cfg)
            txt = (resp.text or "").strip()
            return json.loads(txt)
        except Exception as e:
            msg = repr(e)
            if is_quota_error(msg):
                raise LLMQuotaError(msg)
            if "401" in msg or "403" in msg:
                raise LLMAuthError(msg)
            raise LLMTransientError(msg)