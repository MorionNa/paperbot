from __future__ import annotations
from typing import Any, Dict, Optional
from infra.llm.types import LLMResult


class BaseLLM:
    def generate_text(self, *, system: str, user: str, max_output_tokens: int) -> LLMResult:
        raise NotImplementedError

    def generate_json(self, *, system: str, user: str, schema: Optional[Dict[str, Any]], max_output_tokens: int) -> Dict[str, Any]:
        """
        返回 dict。schema 可选：
        - OpenAI 用 Structured Outputs JSON Schema（最稳）:contentReference[oaicite:6]{index=6}
        - Gemini 用 JSON Mode（mime=application/json）:contentReference[oaicite:7]{index=7}
        - Anthropic 走“严格输出 JSON”提示 + 解析
        """
        raise NotImplementedError