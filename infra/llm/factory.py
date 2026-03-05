from __future__ import annotations
from infra.llm.openai_provider import OpenAILLM
from infra.llm.gemini_provider import GeminiLLM
from infra.llm.anthropic_provider import AnthropicLLM


def make_llm(cfg: dict):
    llm_cfg = cfg.get("llm", {}) or {}
    provider = (llm_cfg.get("provider") or "openai").lower()
    model = llm_cfg.get("model") or ""

    if provider == "openai":
        return OpenAILLM(
            model=model,
            base_url=llm_cfg.get("base_url"),
            api_key_env=llm_cfg.get("api_key_env", "OPENAI_API_KEY"),
        )

    if provider == "gemini":
        return GeminiLLM(model=model)

    if provider == "anthropic":
        return AnthropicLLM(model=model)

    raise ValueError(f"Unknown llm.provider: {provider}")