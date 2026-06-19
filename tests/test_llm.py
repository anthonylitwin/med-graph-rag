from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from packages.llm.profiles import DEFAULT_QWEN3_MODEL, resolve_model_profile
from packages.llm.providers import OllamaChatModel


class ModelProfileTests(unittest.TestCase):
    def test_explicit_profile_wins_over_provider_env(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"MODEL_PROFILE": "frontier", "QA_PROVIDER": "noop", "OPENAI_MODEL": "gpt-custom"},
            clear=True,
        ):
            profile = resolve_model_profile("local-qwen3")

        self.assertEqual(profile.name, "local-qwen3")
        self.assertEqual(profile.qa_provider, "ollama")
        self.assertEqual(profile.qa_model, DEFAULT_QWEN3_MODEL)

    def test_frontier_profile_uses_configured_openai_model(self) -> None:
        with mock.patch.dict(os.environ, {"OPENAI_MODEL": "gpt-custom"}, clear=True):
            profile = resolve_model_profile("frontier")

        self.assertEqual(profile.qa_provider, "openai")
        self.assertEqual(profile.qa_model, "gpt-custom")
        self.assertEqual(profile.extractor_model, "gpt-custom")

    def test_env_provider_override_updates_default_model(self) -> None:
        with mock.patch.dict(os.environ, {"MODEL_PROFILE": "frontier", "QA_PROVIDER": "noop"}, clear=True):
            profile = resolve_model_profile()

        self.assertEqual(profile.name, "frontier")
        self.assertEqual(profile.qa_provider, "noop")
        self.assertEqual(profile.qa_model, "noop-language-model-v0")


class OllamaChatModelTests(unittest.TestCase):
    def test_generate_json_sends_raw_schema_and_parses_message_content(self) -> None:
        calls: list[tuple[object, int]] = []

        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps({"message": {"content": json.dumps({"answer": "ok"})}}).encode("utf-8")

        def fake_urlopen(req: object, timeout: int) -> FakeResponse:
            calls.append((req, timeout))
            return FakeResponse()

        schema = {
            "type": "json_schema",
            "name": "test_schema",
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
            },
        }

        with mock.patch("packages.llm.providers.request.urlopen", fake_urlopen):
            model = OllamaChatModel(model="qwen-test", base_url="http://ollama.test", timeout_seconds=9)
            result = model.generate_json("Answer as JSON", schema)

        req, timeout = calls[0]
        payload = json.loads(req.data.decode("utf-8"))
        self.assertEqual(timeout, 9)
        self.assertEqual(req.full_url, "http://ollama.test/api/chat")
        self.assertEqual(payload["model"], "qwen-test")
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["format"], schema["schema"])
        self.assertEqual(result, {"answer": "ok"})

    def test_generate_json_record_keeps_full_request_and_response(self) -> None:
        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps({"message": {"content": json.dumps({"answer": "ok"})}}).encode("utf-8")

        def fake_urlopen(req: object, timeout: int) -> FakeResponse:
            return FakeResponse()

        schema = {
            "type": "json_schema",
            "name": "test_schema",
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
            },
        }

        with mock.patch("packages.llm.providers.request.urlopen", fake_urlopen):
            model = OllamaChatModel(model="qwen-test", base_url="http://ollama.test", timeout_seconds=9)
            record = model.generate_json_record("Answer as JSON", schema, prompt_version="test_prompt")

        self.assertEqual(record.status, "ok")
        self.assertEqual(record.provider, "ollama")
        self.assertEqual(record.model, "qwen-test")
        self.assertEqual(record.prompt_version, "test_prompt")
        self.assertEqual(record.request["format"], schema["schema"])
        self.assertEqual(record.response_text, json.dumps({"answer": "ok"}))
        self.assertEqual(record.parsed_json, {"answer": "ok"})
        self.assertIn("message", record.to_dict()["raw_response"])


if __name__ == "__main__":
    unittest.main()
