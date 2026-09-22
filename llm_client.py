"""OpenAI-compatible LLM client configuration shared by the CLI tools."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    api_key: str
    base_url: str | None = None


def load_llm_config() -> LLMConfig:
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    if provider == "openai":
        return LLMConfig(provider, os.getenv("OPENAI_API_KEY", ""), os.getenv("OPENAI_BASE_URL"))
    if provider == "local":
        return LLMConfig(
            provider,
            os.getenv("LLM_API_KEY", "local"),
            os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
        )
    if provider == "openrouter":
        return LLMConfig(
            provider,
            os.getenv("OPENROUTER_API_KEY", ""),
            os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1"),
        )
    if provider == "orcarouter":
        return LLMConfig(provider, os.getenv("LLM_API_KEY", ""), os.getenv("LLM_BASE_URL"))
    raise SystemExit(
        "LLM_PROVIDER は openai / local / openrouter / orcarouter のいずれかを指定してください。"
    )


def validate_llm_config() -> LLMConfig:
    config = load_llm_config()
    if not config.api_key:
        key_name = "OPENAI_API_KEY" if config.provider == "openai" else (
            "OPENROUTER_API_KEY" if config.provider == "openrouter" else "LLM_API_KEY"
        )
        raise SystemExit(f"環境変数 {key_name} が設定されていません。")
    if config.provider == "orcarouter" and not config.base_url:
        raise SystemExit("OrcaRouter では環境変数 LLM_BASE_URL が必要です。")
    return config


def create_llm_client():
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise SystemExit(
            "openai パッケージがありません。`pip install openai` を実行してください。"
        ) from exc

    config = validate_llm_config()
    options = {"api_key": config.api_key}
    if config.base_url:
        options["base_url"] = config.base_url
    return OpenAI(**options)


def generate_text(client, model: str, system_prompt: str, user_prompt: str) -> str:
    """Use Chat Completions because most local/OpenAI-compatible servers expose it."""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("LLMからテキスト応答を取得できませんでした。")
    return content.strip()
