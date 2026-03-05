from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class LLMResult:
    text: str
    raw: Optional[Any] = None


class LLMQuotaError(RuntimeError):
    pass


class LLMAuthError(RuntimeError):
    pass


class LLMTransientError(RuntimeError):
    pass


def is_quota_error(msg: str) -> bool:
    s = (msg or "").lower()
    return any(k in s for k in ["429", "quota", "rate limit", "resource_exhausted", "insufficient_quota"])