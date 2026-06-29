from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
import os
from time import perf_counter
from typing import Any, Protocol
from urllib import request

from packages.llm.models import DEFAULT_FRONTIER_MODEL, DEFAULT_REASONING_EFFORT
from packages.llm.profiles import DEFAULT_OLLAMA_MODEL


@dataclass(slots=True)
class ModelCallRecord:
    provider: str
    model: str
    prompt_version: str = ""
    request: dict[str, Any] = field(default_factory=dict)
    json_schema: dict[str, Any] | None = None
    response_text: str = ""
    parsed_json: dict[str, Any] = field(default_factory=dict)
    raw_response: Any = None
    started_at: str = ""
    finished_at: str = ""
    duration_ms: float = 0.0
    status: str = "pending"
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["raw_response"] = _jsonable(self.raw_response)
        return payload


class LanguageModel(Protocol):
    provider: str
    model: str

    def generate_text(self, prompt: str) -> str:
        ...

    def generate_json(self, prompt: str, json_schema: dict[str, Any] | None = None) -> dict[str, Any]:
        ...

    def generate_json_record(
        self,
        prompt: str,
        json_schema: dict[str, Any] | None = None,
        *,
        prompt_version: str = "",
    ) -> ModelCallRecord:
        ...


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(child) for key, child in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(child) for child in value]
    if hasattr(value, "model_dump"):
        try:
            return _jsonable(value.model_dump(mode="json"))
        except TypeError:
            return _jsonable(value.model_dump())
    if hasattr(value, "__dict__"):
        return _jsonable(vars(value))
    return str(value)


def _record_json_call(
    provider: str,
    model: str,
    request_payload: dict[str, Any],
    json_schema: dict[str, Any] | None,
    prompt_version: str,
    call,
) -> ModelCallRecord:
    started = _now_iso()
    start = perf_counter()
    record = ModelCallRecord(
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        request=request_payload,
        json_schema=json_schema,
        started_at=started,
    )
    try:
        raw_response = call()
        record.raw_response = raw_response
        text = response_text(raw_response)
        record.response_text = text
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise RuntimeError("Model JSON response must be an object")
        record.parsed_json = parsed
        record.status = "ok"
    except Exception as exc:  # noqa: BLE001 - recorded for audit before caller handles it.
        record.status = "error"
        record.error = str(exc)
    finally:
        record.finished_at = _now_iso()
        record.duration_ms = round((perf_counter() - start) * 1000, 3)
    return record


def _raise_if_error(record: ModelCallRecord) -> dict[str, Any]:
    if record.status != "ok":
        raise RuntimeError(record.error or "Model JSON call failed")
    return record.parsed_json


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

    def _response_kwargs(self, prompt: str, json_schema: dict[str, Any] | None = None) -> dict[str, Any]:
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
        return kwargs

    def _create_response(self, prompt: str, json_schema: dict[str, Any] | None = None) -> Any:
        return self.client.responses.create(**self._response_kwargs(prompt, json_schema))

    def generate_text(self, prompt: str) -> str:
        return response_text(self._create_response(prompt))

    def generate_json(self, prompt: str, json_schema: dict[str, Any] | None = None) -> dict[str, Any]:
        return _raise_if_error(self.generate_json_record(prompt, json_schema))

    def generate_json_record(
        self,
        prompt: str,
        json_schema: dict[str, Any] | None = None,
        *,
        prompt_version: str = "",
    ) -> ModelCallRecord:
        kwargs = self._response_kwargs(prompt, json_schema)
        return _record_json_call(
            self.provider,
            self.model,
            kwargs,
            json_schema,
            prompt_version,
            lambda: self.client.responses.create(**kwargs),
        )


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
        return _raise_if_error(self.generate_json_record(prompt, json_schema))

    def generate_json_record(
        self,
        prompt: str,
        json_schema: dict[str, Any] | None = None,
        *,
        prompt_version: str = "",
    ) -> ModelCallRecord:
        payload = {"model": self.model, "prompt": prompt, "json_schema": json_schema}
        started = _now_iso()
        start = perf_counter()
        record = ModelCallRecord(
            provider=self.provider,
            model=self.model,
            prompt_version=prompt_version,
            request=payload,
            json_schema=json_schema,
            started_at=started,
        )
        try:
            result = self._post(payload)
            record.raw_response = result
            if isinstance(result.get("json"), dict):
                record.parsed_json = result["json"]
                record.response_text = json.dumps(record.parsed_json, ensure_ascii=True)
                record.status = "ok"
                return record
            text = result.get("text") or result.get("output") or result.get("answer")
            if isinstance(text, str):
                record.response_text = text
                parsed = json.loads(text)
                if not isinstance(parsed, dict):
                    raise RuntimeError("Local model JSON response must be an object")
                record.parsed_json = parsed
                record.status = "ok"
                return record
            record.parsed_json = result
            record.response_text = json.dumps(result, ensure_ascii=True)
            record.status = "ok"
            return record
        except Exception as exc:  # noqa: BLE001
            record.status = "error"
            record.error = str(exc)
            return record
        finally:
            record.finished_at = _now_iso()
            record.duration_ms = round((perf_counter() - start) * 1000, 3)


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
        return _raise_if_error(self.generate_json_record(prompt, json_schema))

    def generate_json_record(
        self,
        prompt: str,
        json_schema: dict[str, Any] | None = None,
        *,
        prompt_version: str = "",
    ) -> ModelCallRecord:
        request_payload: dict[str, Any] = {
            "model": self.model,
            "endpoint": f"{self.base_url}/api/chat",
            "timeout_seconds": self.timeout_seconds,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0},
        }
        ollama_schema = _json_schema_for_ollama(json_schema)
        if ollama_schema is not None:
            request_payload["format"] = ollama_schema

        started = _now_iso()
        start = perf_counter()
        record = ModelCallRecord(
            provider=self.provider,
            model=self.model,
            prompt_version=prompt_version,
            request=request_payload,
            json_schema=json_schema,
            started_at=started,
        )
        try:
            result = self._post_chat(prompt, json_schema)
            record.raw_response = result
            content = self._content(result).strip()
            record.response_text = content
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise RuntimeError("Ollama JSON response must be an object")
            record.parsed_json = parsed
            record.status = "ok"
        except json.JSONDecodeError as exc:
            record.status = "error"
            record.error = "Ollama model response was not valid JSON"
            record.raw_response = record.raw_response or {"decode_error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            record.status = "error"
            record.error = f"Ollama request failed at {self.base_url}/api/chat: {exc}"
        finally:
            record.finished_at = _now_iso()
            record.duration_ms = round((perf_counter() - start) * 1000, 3)
        return record


class NoopLanguageModel:
    provider = "noop"

    def __init__(self, model: str = "noop-language-model-v0") -> None:
        self.model = model

    def generate_text(self, prompt: str) -> str:
        return f"Noop response for prompt length {len(prompt)}."

    def generate_json(self, prompt: str, json_schema: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.generate_json_record(prompt, json_schema).parsed_json

    def generate_json_record(
        self,
        prompt: str,
        json_schema: dict[str, Any] | None = None,
        *,
        prompt_version: str = "",
    ) -> ModelCallRecord:
        parsed_json = {
            "answer": "Noop model did not generate a substantive answer.",
            "sources": [],
            "reasoningPath": [],
            "confidence": 0.0,
            "abstained": True,
        }
        now = _now_iso()
        return ModelCallRecord(
            provider=self.provider,
            model=self.model,
            prompt_version=prompt_version,
            request={"model": self.model, "prompt": prompt, "json_schema": json_schema},
            json_schema=json_schema,
            response_text=json.dumps(parsed_json, ensure_ascii=True),
            parsed_json=parsed_json,
            raw_response=parsed_json,
            started_at=now,
            finished_at=now,
            duration_ms=0.0,
            status="ok",
        )


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
    "ModelCallRecord",
    "OpenAIResponsesModel",
    "LocalHTTPModel",
    "OllamaChatModel",
    "NoopLanguageModel",
    "get_language_model",
    "response_text",
]
