from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


DEFAULT_PROVIDER = "openai"

PROVIDERS: dict[str, dict[str, Any]] = {
    "openai": {
        "api_key_env": "OPENAI_API_KEY",
        "model_env": "OPENAI_MODEL",
        "base_url_env": None,
        "default_base_url": None,
        "default_model": None,
        "api_style": "responses",
    },
    "local": {
        "api_key_env": "LOCAL_LLM_API_KEY",
        "model_env": "LOCAL_LLM_MODEL",
        "base_url_env": "LOCAL_LLM_BASE_URL",
        "default_base_url": "http://localhost:11434/v1",
        "default_model": None,
        "api_style": "chat_completions",
    },
    "orcarouter": {
        "api_key_env": "ORCAROUTER_API_KEY",
        "model_env": "ORCAROUTER_MODEL",
        "base_url_env": "ORCAROUTER_BASE_URL",
        "default_base_url": "https://api.orcarouter.ai/v1",
        "default_model": "orcarouter/auto",
        "api_style": "chat_completions",
    },
}

_ENV_LOADED = False


def _ensure_env_loaded() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    if load_dotenv is not None:
        load_dotenv()
    _ENV_LOADED = True


def get_provider() -> str:
    _ensure_env_loaded()
    provider = os.getenv("LLM_PROVIDER", "").strip().lower() or DEFAULT_PROVIDER
    if provider not in PROVIDERS:
        valid = " / ".join(PROVIDERS)
        raise SystemExit(
            f"不明な LLM_PROVIDER です: {provider}（{valid} のいずれかを指定してください）"
        )
    return provider


def resolve_model(provider: str, cli_model: str | None) -> str:
    if cli_model:
        return cli_model

    config = PROVIDERS[provider]
    env_value = os.getenv(config["model_env"], "").strip()
    if env_value:
        return env_value

    if config["default_model"]:
        return config["default_model"]

    raise SystemExit(
        f"モデル名が未設定です。環境変数 {config['model_env']} を設定するか、"
        "--model で指定してください。"
    )


def _require_openai_sdk():
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise SystemExit(
            "openai パッケージがインストールされていません。`pip install openai` を実行してください。"
        ) from exc
    return OpenAI


@dataclass(frozen=True)
class LLMClient:
    provider: str
    api_style: str
    client: Any

    def complete(self, model: str, system_prompt: str, user_prompt: str) -> str:
        if self.api_style == "responses":
            response = self.client.responses.create(
                model=model,
                input=[
                    {
                        "role": "system",
                        "content": [{"type": "input_text", "text": system_prompt}],
                    },
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": user_prompt}],
                    },
                ],
            )
            return response.output_text.strip()

        response = self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content.strip()


def build_llm_client(provider: str) -> LLMClient:
    _ensure_env_loaded()
    config = PROVIDERS[provider]

    api_key = os.getenv(config["api_key_env"], "").strip()
    if not api_key:
        raise SystemExit(f"環境変数 {config['api_key_env']} が設定されていません。")

    base_url = None
    if config["base_url_env"]:
        base_url = (
            os.getenv(config["base_url_env"], "").strip()
            or config["default_base_url"]
        )

    OpenAI = _require_openai_sdk()
    client_kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url

    client = OpenAI(**client_kwargs)
    return LLMClient(provider=provider, api_style=config["api_style"], client=client)
