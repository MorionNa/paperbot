# infra/secrets.py
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml

def load_secrets_into_env(base_dir: Path, rel_path: str = "config/secrets.yml") -> None:
    """
    Load secrets from YAML and set into os.environ for SDKs to read.
    Expected keys in secrets.yml (any subset is ok):
      openai_api_key / gemini_api_key / anthropic_api_key
    """
    p = (base_dir / rel_path).resolve()
    if not p.exists():
        return  # 没有 secrets.yml 就跳过（方便你在别的机器上跑）

    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}

    mapping = {
        "openai_api_key": "OPENAI_API_KEY",
        "gemini_api_key": "GEMINI_API_KEY",
        "anthropic_api_key": "ANTHROPIC_API_KEY",
        "dashscope_api_key": "DASHSCOPE_API_KEY",  # 加这行
        "elsevier_api_key": "ELSEVIER_API_KEY",
        "elsevier_insttoken": "ELSEVIER_INSTTOKEN",
        "wiley_tdm_client_token": "WILEY_TDM_CLIENT_TOKEN",
        "springer_api_key": "SPRINGER_API_KEY",
        "ieee_api_key": "IEEE_API_KEY",
        "custom_llm_api_key": "CUSTOM_LLM_API_KEY",
        "deepseek_api_key": "DEEPSEEK_API_KEY",
        "zhipu_api_key": "ZHIPU_API_KEY",
        "yuanbao_api_key": "YUANBAO_API_KEY",
    }

    for k, env_name in mapping.items():
        v = (data.get(k) or "").strip()
        if v and not os.environ.get(env_name):
            os.environ[env_name] = v
