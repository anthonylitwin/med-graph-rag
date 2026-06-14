from __future__ import annotations

import json
import os
from typing import Any, Protocol
from urllib import request

from packages.llm.models import DEFAULT_FRONTIER_MODEL, DEFAULT_REASONING_EFFORT
from packages.llm.profiles import DEFAULT_OLLAMA_MODEL


class LanguageModel(Protocol):
    provider: str
    model: str

    def generate_text(self, prompt: str) -> str:
        ...

    def generate_json(self, prompt: str, json_schema: dict[str, Any] | None = None) -> dict[str, Any]:
        ...


def response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    if hasattr(response, "model_dump"):
        response = response.model_dump()
    elif not isinstance(response, dict) and hasattr(response, "__dict__"):
        response = vars(response)

    def walk(value: Any) -> str | None:
        if isinstance(value, dict):
            if value.get("type") == "output_text" and isinstance(value.get("text"), str):
                return value["text"]
            for child in value.values():
                result = walk(child)
                if result:
                    return result
        if isinstance(value, list):
            for child in value:
                result = walk(child)
                if result:
                    return result
        return None

    text = walk(response)
    if not text:
        raise RuntimeError("Model response did not contain output text")
    return text


class OpenAIResponsesModel:
    provider = "openai"

    def __init__(
        self,
        model: str | None = None,
        reasoning_effort: str | None = None,
        provider: str | None = None,
    ) -> None:
        self.provider = provider or self.provider
        self.model = model or os.getenv("OPENAI_MODEL", DEFAULT_FRONTIER_MODEL)
        self.reasoning_effort = reasoning_effort or os.getenv("OPENAI_REASONING_EFFORT", DEFAULT_REASONING_EFFORT)

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install the openai package to use the OpenAI Responses model provider") from exc

        self.client = OpenAI()

    def _create_response(self, prompt: str, json_schema: dict[str, Any] | None = None) -> Any:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": prompt}],
                }
            ],
            "reasoning": {"effort": self.reasoning_effort},
        }
        if json_schema is not None:
            kwargs["text"] = {"format": json_schema}
        return self.client.responses.create(**kwargs)

    def generate_text(self, prompt: str) -> str:
        return response_text(self._create_response(prompt))

    def generate_json(self, prompt: str, json_schema: dict[str, Any] | None = None) -> dict[str, Any]:
        return json.loads(response_text(self._create_response(prompt, json_schema)))


class LocalHTTPModel:
    provider = "local"

    def __init__(self, model: str | None = None, endpoint: str | None = None) -> None:
        self.model = model or os.getenv("LOCAL_MODEL", "local-model")
        self.endpoint = endpoint or os.getenv("LOCAL_MODEL_URL", "http://localhost:8001/generate")

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self.endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=120) as response:  # noqa: S310 - local/dev endpoint by configuration.
            return json.loads(response.read().decode("utf-8"))

    def generate_text(self, prompt: str) -> str:
        result = self._post({"model": self.model, "prompt": prompt})
        text = result.get("text") or result.get("output") or result.get("answer")
        if not isinstance(text, str):
            raise RuntimeError("Local model response did not include text")
        return text

    def generate_json(self, prompt: str, json_schema: dict[str, Any] | None = None) -> dict[str, Any]:
        result = self._post({"model": self.model, "prompt": prompt, "json_schema": json_schema})
        if isinstance(result.get("json"), dict):
            return result["json"]
        text = result.get("text") or result.get("output") or result.get("answer")
        if isinstance(text, str):
            return json.loads(text)
        return result


def _json_schema_for_ollama(json_schema: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(json_schema, dict):
        return None
    if json_schema.get("type") == "json_schema" and isinstance(json_schema.get("schema"), dict):
        return json_schema["schema"]
    return json_schema


class OllamaChatModel:
    provider = "ollama"

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self.model = model or os.getenv("LOCAL_MODEL", DEFAULT_OLLAMA_MODEL)
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.timeout_seconds = timeout_seconds or int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))

    def _post_chat(self, prompt: str, json_schema: dict[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0},
        }
        ollama_schema = _json_schema_for_ollama(json_schema)
        if ollama_schema is not None:
            payload["format"] = ollama_schema

        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=self.timeout_seconds) as response:  # noqa: S310 - local/dev endpoint.
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _content(result: dict[str, Any]) -> str:
        message = result.get("message")
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return message["content"]
        if isinstance(result.get("response"), str):
            return result["response"]
        raise RuntimeError("Ollama response did not include message content")

    def generate_text(self, prompt: str) -> str:
        return self._content(self._post_chat(prompt))

    def generate_json(self, prompt: str, json_schema: dict[str, Any] | None = None) -> dict[str, Any]:
        content = self._content(self._post_chat(prompt, json_schema)).strip()
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Ollama model response was not valid JSON") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("Ollama JSON response must be an object")
        return parsed


class NoopLanguageModel:
    provider = "noop"

    def __init__(self, model: str = "noop-language-model-v0") -> None:
        self.model = model

    def generate_text(self, prompt: str) -> str:
        return f"Noop response for prompt length {len(prompt)}."

    def generate_json(self, prompt: str, json_schema: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "answer": "Noop model did not generate a substantive answer.",
            "sources": [],
            "reasoningPath": [],
            "confidence": 0.0,
            "abstained": True,
        }


def get_language_model(provider: str, model: str | None = None) -> LanguageModel:
    normalized = provider.lower().strip()
    if normalized == "openai":
        return OpenAIResponsesModel(model=model)
    if normalized in {"fine_tuned", "fine-tuned", "finetuned"}:
        return OpenAIResponsesModel(model=model, provider="fine_tuned")
    if normalized == "local":
        return LocalHTTPModel(model=model)
    if normalized == "ollama":
        return OllamaChatModel(model=model)
    if normalized in {"noop", "none"}:
        return NoopLanguageModel(model=model or "noop-language-model-v0")
    raise ValueError(f"Unsupported language model provider: {provider}")


__all__ = [
    "LanguageModel",
    "OpenAIResponsesModel",
    "LocalHTTPModel",
    "OllamaChatModel",
    "NoopLanguageModel",
    "get_language_model",
    "response_text",
]
