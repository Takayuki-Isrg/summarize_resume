import os
import unittest
from unittest.mock import patch

from llm_client import generate_text, load_llm_config


class _Message:
    content = "  要約結果  "


class _Completion:
    choices = [type("Choice", (), {"message": _Message()})]


class _Completions:
    def create(self, **kwargs):
        self.kwargs = kwargs
        return _Completion()


class LLMClientTest(unittest.TestCase):
    def test_local_defaults_to_ollama_compatible_endpoint(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "local"}, clear=True):
            config = load_llm_config()
        self.assertEqual(config.base_url, "http://localhost:11434/v1")
        self.assertEqual(config.api_key, "local")

    def test_openrouter_uses_its_key_and_endpoint(self):
        with patch.dict(
            os.environ,
            {"LLM_PROVIDER": "openrouter", "OPENROUTER_API_KEY": "test-key"},
            clear=True,
        ):
            config = load_llm_config()
        self.assertEqual(config.base_url, "https://openrouter.ai/api/v1")
        self.assertEqual(config.api_key, "test-key")

    def test_generate_text_uses_chat_completions(self):
        completions = _Completions()
        client = type(
            "Client",
            (),
            {"chat": type("Chat", (), {"completions": completions})()},
        )()
        result = generate_text(client, "model", "system", "user")
        self.assertEqual(result, "要約結果")
        self.assertEqual(completions.kwargs["model"], "model")


if __name__ == "__main__":
    unittest.main()
