import pytest

import llm_provider
from llm_provider import (
    LLMClient,
    build_llm_client,
    get_provider,
    resolve_model,
)


@pytest.fixture(autouse=True)
def _no_dotenv_loading(monkeypatch):
    # .env の実ファイル読み込みをテストから遮断し、os.environ の状態だけに依存させる。
    monkeypatch.setattr(llm_provider, "_ENV_LOADED", True)


@pytest.fixture(autouse=True)
def _clean_provider_env(monkeypatch):
    for key in [
        "LLM_PROVIDER",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "LOCAL_LLM_BASE_URL",
        "LOCAL_LLM_API_KEY",
        "LOCAL_LLM_MODEL",
        "ORCAROUTER_API_KEY",
        "ORCAROUTER_BASE_URL",
        "ORCAROUTER_MODEL",
    ]:
        monkeypatch.delenv(key, raising=False)


class FakeOpenAI:
    last_kwargs = None

    def __init__(self, **kwargs):
        FakeOpenAI.last_kwargs = kwargs


@pytest.fixture
def fake_openai_sdk(monkeypatch):
    FakeOpenAI.last_kwargs = None
    monkeypatch.setattr(llm_provider, "_require_openai_sdk", lambda: FakeOpenAI)
    return FakeOpenAI


# --- get_provider ---


def test_get_provider_defaults_to_openai():
    assert get_provider() == "openai"


def test_get_provider_reads_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    assert get_provider() == "local"


def test_get_provider_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "OrcaRouter")
    assert get_provider() == "orcarouter"


def test_get_provider_rejects_unknown_value(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "bogus")
    with pytest.raises(SystemExit):
        get_provider()


# --- resolve_model ---


def test_resolve_model_prefers_cli_value():
    assert resolve_model("openai", "gpt-4.1-mini") == "gpt-4.1-mini"


def test_resolve_model_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1")
    assert resolve_model("openai", None) == "gpt-4.1"


def test_resolve_model_orcarouter_has_builtin_default():
    assert resolve_model("orcarouter", None) == "orcarouter/auto"


def test_resolve_model_raises_clear_error_when_unset():
    with pytest.raises(SystemExit, match="LOCAL_LLM_MODEL"):
        resolve_model("local", None)


# --- build_llm_client ---


def test_build_llm_client_raises_when_api_key_missing(fake_openai_sdk):
    with pytest.raises(SystemExit, match="ORCAROUTER_API_KEY"):
        build_llm_client("orcarouter")


def test_build_llm_client_openai_uses_default_base_url(monkeypatch, fake_openai_sdk):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    client = build_llm_client("openai")

    assert client.provider == "openai"
    assert client.api_style == "responses"
    assert fake_openai_sdk.last_kwargs == {"api_key": "sk-test"}


def test_build_llm_client_local_uses_configured_base_url(monkeypatch, fake_openai_sdk):
    monkeypatch.setenv("LOCAL_LLM_API_KEY", "ollama")
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
    client = build_llm_client("local")

    assert client.api_style == "chat_completions"
    assert fake_openai_sdk.last_kwargs == {
        "api_key": "ollama",
        "base_url": "http://localhost:11434/v1",
    }


def test_build_llm_client_orcarouter_falls_back_to_default_base_url(
    monkeypatch, fake_openai_sdk
):
    monkeypatch.setenv("ORCAROUTER_API_KEY", "or-test")
    client = build_llm_client("orcarouter")

    assert client.api_style == "chat_completions"
    assert fake_openai_sdk.last_kwargs == {
        "api_key": "or-test",
        "base_url": "https://api.orcarouter.ai/v1",
    }


# --- LLMClient.complete ---


class FakeResponsesClient:
    def __init__(self, output_text):
        self.responses = self
        self._output_text = output_text
        self.last_call = None

    def create(self, **kwargs):
        self.last_call = kwargs
        return type("Response", (), {"output_text": self._output_text})()


class FakeChatCompletionsClient:
    def __init__(self, content):
        self.chat = self
        self.completions = self
        self._content = content
        self.last_call = None

    def create(self, **kwargs):
        self.last_call = kwargs
        message = type("Message", (), {"content": self._content})()
        choice = type("Choice", (), {"message": message})()
        return type("Response", (), {"choices": [choice]})()


def test_complete_uses_responses_api_for_openai_style():
    fake_client = FakeResponsesClient(" 要約結果 \n")
    llm_client = LLMClient(provider="openai", api_style="responses", client=fake_client)

    result = llm_client.complete("gpt-4.1-mini", "system prompt", "user prompt")

    assert result == "要約結果"
    assert fake_client.last_call["model"] == "gpt-4.1-mini"


def test_complete_uses_chat_completions_for_local_and_orcarouter_style():
    fake_client = FakeChatCompletionsClient(" スカウトメール \n")
    llm_client = LLMClient(
        provider="orcarouter", api_style="chat_completions", client=fake_client
    )

    result = llm_client.complete("orcarouter/auto", "system prompt", "user prompt")

    assert result == "スカウトメール"
    assert fake_client.last_call["messages"] == [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "user prompt"},
    ]
