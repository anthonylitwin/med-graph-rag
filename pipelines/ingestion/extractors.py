from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol

from pipelines.ingestion.models import ChunkRecord, DEFAULT_OPENAI_MODEL, DEFAULT_PROMPT_VERSION


PROMPT_PATH = Path(__file__).resolve().parents[2] / "packages/graph/schema/001_initial_prompt.md"


class BiomedicalExtractor(Protocol):
    provider: str
    model: str

    def extract(self, document: dict[str, Any], chunk: ChunkRecord) -> dict[str, Any]:
        ...


def extraction_json_schema() -> dict[str, Any]:
    string = {"type": "string"}
    entity_ref = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"id": string, "type": string, "name": string},
        "required": ["id", "type", "name"],
    }
    return {
        "type": "json_schema",
        "name": "medgraphrag_extraction",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "paper": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "pmid": string,
                        "pmcid": string,
                        "title": string,
                        "year": string,
                        "journal": string,
                        "doi": string,
                        "authors": {"type": "array", "items": string},
                        "abstract": string,
                    },
                    "required": ["pmid", "pmcid", "title", "year", "journal", "doi", "authors", "abstract"],
                },
                "entities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "id": string,
                            "type": string,
                            "name": string,
                            "properties": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "source": string,
                                    "extractor": string,
                                    "model": string,
                                    "created_at": string,
                                },
                                "required": ["source", "extractor", "model", "created_at"],
                            },
                        },
                        "required": ["id", "type", "name", "properties"],
                    },
                },
                "relationships": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "type": string,
                            "source": entity_ref,
                            "target": entity_ref,
                            "properties": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "confidence": {"type": "number"},
                                    "evidence": string,
                                    "source_pmid": string,
                                    "source_pmcid": string,
                                    "chunk_id": string,
                                    "extractor": string,
                                    "model": string,
                                    "prompt_version": string,
                                    "created_at": string,
                                },
                                "required": [
                                    "confidence",
                                    "evidence",
                                    "source_pmid",
                                    "source_pmcid",
                                    "chunk_id",
                                    "extractor",
                                    "model",
                                    "prompt_version",
                                    "created_at",
                                ],
                            },
                        },
                        "required": ["type", "source", "target", "properties"],
                    },
                },
                "rejected_candidates": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {"text": string, "reason": string},
                        "required": ["text", "reason"],
                    },
                },
            },
            "required": ["paper", "entities", "relationships", "rejected_candidates"],
        },
    }


def _format_prompt(document: dict[str, Any], chunk: ChunkRecord) -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    replacements = {
        "pmid": str(document.get("pmid") or ""),
        "pmcid": str(document.get("pmcid") or chunk.pmcid),
        "chunk_id": chunk.id,
        "chunk_section": chunk.section,
        "title": str(document.get("title") or ""),
        "year": str(document.get("year") or ""),
        "journal": str(document.get("journal") or ""),
        "doi": str(document.get("doi") or ""),
        "authors": json.dumps(document.get("authors") or []),
        "chunk_text": chunk.text,
    }
    prompt = template
    for key, value in replacements.items():
        prompt = prompt.replace("{{" + key + "}}", value)
    return prompt


def _response_text(response: Any) -> str:
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
        raise RuntimeError("OpenAI response did not contain output text")
    return text


class OpenAIResponsesExtractor:
    provider = "openai"

    def __init__(self, model: str | None = None, reasoning_effort: str | None = None) -> None:
        self.model = model or os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
        self.reasoning_effort = reasoning_effort or os.getenv("OPENAI_REASONING_EFFORT", "medium")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install the openai package to use --extractor openai") from exc

        self.client = OpenAI()

    def extract(self, document: dict[str, Any], chunk: ChunkRecord) -> dict[str, Any]:
        response = self.client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": _format_prompt(document, chunk)}],
                }
            ],
            reasoning={"effort": self.reasoning_effort},
            text={"format": extraction_json_schema()},
        )
        return json.loads(_response_text(response))


class NoopExtractor:
    provider = "noop"

    def __init__(self, model: str = "noop-extractor-v0") -> None:
        self.model = model

    def extract(self, document: dict[str, Any], chunk: ChunkRecord) -> dict[str, Any]:
        return {
            "paper": {
                "pmid": str(document.get("pmid") or ""),
                "pmcid": str(document.get("pmcid") or chunk.pmcid),
                "title": str(document.get("title") or ""),
                "year": str(document.get("year") or ""),
                "journal": str(document.get("journal") or ""),
                "doi": str(document.get("doi") or ""),
                "authors": document.get("authors") or [],
                "abstract": "",
            },
            "entities": [],
            "relationships": [],
            "rejected_candidates": [],
        }


class StaticFixtureExtractor:
    provider = "fixture"

    def __init__(self, outputs_by_chunk_id: dict[str, dict[str, Any]], model: str = "fixture-extractor-v0") -> None:
        self.outputs_by_chunk_id = outputs_by_chunk_id
        self.model = model

    def extract(self, document: dict[str, Any], chunk: ChunkRecord) -> dict[str, Any]:
        return self.outputs_by_chunk_id.get(chunk.id, NoopExtractor(self.model).extract(document, chunk))


def get_extractor(provider: str, model: str | None = None) -> BiomedicalExtractor:
    normalized = provider.lower().strip()
    if normalized == "openai":
        return OpenAIResponsesExtractor(model=model)
    if normalized in {"noop", "none"}:
        return NoopExtractor(model=model or "noop-extractor-v0")
    raise ValueError(f"Unsupported extractor provider: {provider}")


__all__ = [
    "BiomedicalExtractor",
    "OpenAIResponsesExtractor",
    "NoopExtractor",
    "StaticFixtureExtractor",
    "get_extractor",
    "extraction_json_schema",
    "DEFAULT_PROMPT_VERSION",
]
