from __future__ import annotations
import json
from typing import Any, Dict, Optional

import anthropic

from infra.llm.base import BaseLLM
from infra.llm.types import LLMResult, LLMQuotaError, LLMAuthError, LLMTransientError, is_quota_error


class AnthropicLLM(BaseLLM):
    def __init__(self, model: str):
        self.model = model
        self.client = anthropic.Anthropic()  # uses ANTHROPIC_API_KEY :contentReference[oaicite:12]{index=12}

    def generate_text(self, *, system: str, user: str, max_output_tokens: int) -> LLMResult:
        try:
            msg = self.client.messages.create(
                model=self.model,
                max_tokens=max_output_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            # content 是一组 block；常见第一个是 text
            text = "".join([b.text for b in msg.content if getattr(b, "type", "") == "text"])
            return LLMResult(text=text, raw=msg)
        except Exception as e:
            s = repr(e)
            if is_quota_error(s):
                raise LLMQuotaError(s)
            if "401" in s or "403" in s:
                raise LLMAuthError(s)
            raise LLMTransientError(s)

    def generate_json(self, *, system: str, user: str, schema: Optional[Dict[str, Any]], max_output_tokens: int) -> Dict[str, Any]:
        prompt = user + "\n\n请只输出 JSON（不加markdown）。"
        out = self.generate_text(system=system, user=prompt, max_output_tokens=max_output_tokens).text.strip()
        return json.loads(out)