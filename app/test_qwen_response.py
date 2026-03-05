from openai import OpenAI
from pathlib import Path
import os

from infra.secrets import load_secrets_into_env

BASE_DIR = Path(__file__).resolve().parents[1]   # 项目根目录 E:\paperbot
load_secrets_into_env(BASE_DIR)                  # 把 secrets.yml 注入到 os.environ

client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/api/v2/apps/protocols/compatible-mode/v1",
)

resp = client.responses.create(
    model="qwen3.5-plus",
    input="用一句话介绍你自己"
)

print(resp.output_text)