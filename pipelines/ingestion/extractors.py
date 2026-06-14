from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol

from packages.llm.profiles import DEFAULT_GLINER_BIOMED_MODEL, DEFAULT_OLLAMA_MODEL
from packages.llm.providers import LanguageModel, OpenAIResponsesModel, get_language_model
from pipelines.ingestion.models import ChunkRecord, DEFAULT_OPENAI_MODEL, DEFAULT_PROMPT_VERSION


PROMPT_PATH = Path(__file__).resolve().parents[2] / "packages/graph/schema/001_initial_prompt.md"
BIOMEDICAL_LABELS = ("Drug", "Condition", "Symptom", "RiskFactor", "Biomarker")
RELATIONSHIP_TYPES = (
    "TREATS",
    "PREVENTS",
    "REDUCES",
    "INCREASES",
    "ASSOCIATED_WITH",
    "HAS_ADVERSE_EFFECT",
    "CAUSES",
    "HAS_SYMPTOM",
    "INCREASES_RISK_OF",
    "INTERACTS_WITH",
    "CONTRAINDICATED_FOR",
)
RELATIONSHIP_DIRECTIONS = (
    "TREATS: Drug -> Condition",
    "PREVENTS: Drug -> Condition",
    "REDUCES: Drug -> Biomarker",
    "INCREASES: Drug -> Biomarker",
    "ASSOCIATED_WITH: any biomedical entity -> any biomedical entity",
    "HAS_ADVERSE_EFFECT: Drug -> Condition",
    "CAUSES: Condition -> Condition",
    "HAS_SYMPTOM: Condition -> Symptom",
    "INCREASES_RISK_OF: RiskFactor -> Condition",
    "INTERACTS_WITH: Drug -> Drug",
    "CONTRAINDICATED_FOR: Drug -> Condition",
)


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


def relationship_extraction_json_schema() -> dict[str, Any]:
    string = {"type": "string"}
    entity_ref = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"type": string, "name": string},
        "required": ["type", "name"],
    }
    return {
        "type": "json_schema",
        "name": "medgraphrag_local_relationship_extraction",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
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
                                },
                                "required": ["confidence", "evidence"],
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
            "required": ["relationships", "rejected_candidates"],
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


def _paper_payload(document: dict[str, Any], chunk: ChunkRecord) -> dict[str, Any]:
    return {
        "pmid": str(document.get("pmid") or ""),
        "pmcid": str(document.get("pmcid") or chunk.pmcid),
        "title": str(document.get("title") or ""),
        "year": str(document.get("year") or ""),
        "journal": str(document.get("journal") or ""),
        "doi": str(document.get("doi") or ""),
        "authors": document.get("authors") if isinstance(document.get("authors"), list) else [],
        "abstract": str(document.get("abstract") or ""),
    }


def _canonical_label(value: Any) -> str | None:
    normalized = str(value or "").replace("_", "").replace(" ", "").lower()
    for label in BIOMEDICAL_LABELS:
        if normalized == label.lower():
            return label
    return None


def _candidate_name(candidate: dict[str, Any]) -> str:
    for key in ("text", "name", "span"):
        value = candidate.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _relationship_prompt(document: dict[str, Any], chunk: ChunkRecord, entities: list[dict[str, Any]]) -> str:
    payload = {
        "document": {
            "pmid": str(document.get("pmid") or ""),
            "pmcid": str(document.get("pmcid") or chunk.pmcid),
            "title": str(document.get("title") or ""),
        },
        "chunk": {
            "id": chunk.id,
            "section": chunk.section,
            "text": chunk.text,
        },
        "candidate_entities": [{"type": item["type"], "name": item["name"]} for item in entities],
    }
    return (
        "You extract simple biomedical knowledge graph relationships for MedGraphRAG.\n"
        "Use only the chunk text and only the supplied candidate entities.\n"
        "Return relationships only when the text explicitly supports them.\n"
        "Each evidence value must be a short exact quote or close excerpt from the chunk.\n"
        "Do not invent entities, facts, identifiers, citations, or outside medical knowledge.\n\n"
        "Allowed relationship types and directions:\n"
        + "\n".join(f"- {item}" for item in RELATIONSHIP_DIRECTIONS)
        + "\n\n"
        "Input JSON:\n"
        f"{json.dumps(payload, indent=2)}\n"
    )


class OpenAIResponsesExtractor:
    provider = "openai"

    def __init__(self, model: str | None = None, reasoning_effort: str | None = None) -> None:
        self.model = model or os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
        self.reasoning_effort = reasoning_effort or os.getenv("OPENAI_REASONING_EFFORT", "medium")
        self.language_model = OpenAIResponsesModel(model=self.model, reasoning_effort=self.reasoning_effort)

    def extract(self, document: dict[str, Any], chunk: ChunkRecord) -> dict[str, Any]:
        return self.language_model.generate_json(_format_prompt(document, chunk), extraction_json_schema())


class GLiNEROllamaExtractor:
    provider = "gliner_ollama"

    def __init__(
        self,
        model: str | None = None,
        entity_model: str | None = None,
        entity_threshold: float | None = None,
        language_model: LanguageModel | None = None,
        gliner_model: Any | None = None,
    ) -> None:
        self.relation_model = model or os.getenv("EXTRACTOR_MODEL") or os.getenv("LOCAL_MODEL", DEFAULT_OLLAMA_MODEL)
        self.entity_model = entity_model or os.getenv("EXTRACTOR_ENTITY_MODEL", DEFAULT_GLINER_BIOMED_MODEL)
        self.entity_threshold = entity_threshold or float(os.getenv("GLINER_ENTITY_THRESHOLD", "0.35"))
        self.model = f"{self.entity_model} + {self.relation_model}"
        self.language_model = language_model or get_language_model("ollama", self.relation_model)
        self._gliner_model = gliner_model

    def _load_gliner_model(self) -> Any:
        if self._gliner_model is None:
            try:
                from gliner import GLiNER
            except ImportError as exc:
                raise RuntimeError(
                    "Install local model dependencies with requirements-local-models.txt to use gliner_ollama"
                ) from exc
            self._gliner_model = GLiNER.from_pretrained(self.entity_model)
        return self._gliner_model

    def _extract_entities(self, chunk: ChunkRecord) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        raw_candidates = self._load_gliner_model().predict_entities(
            chunk.text,
            list(BIOMEDICAL_LABELS),
            threshold=self.entity_threshold,
        )
        entities_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        rejected: list[dict[str, str]] = []
        for raw_candidate in raw_candidates if isinstance(raw_candidates, list) else []:
            if not isinstance(raw_candidate, dict):
                rejected.append({"text": str(raw_candidate), "reason": "GLiNER candidate is not an object"})
                continue
            entity_type = _canonical_label(raw_candidate.get("label") or raw_candidate.get("type"))
            name = _candidate_name(raw_candidate)
            if entity_type is None or not name:
                rejected.append({"text": str(raw_candidate), "reason": "GLiNER candidate has unsupported type or missing text"})
                continue
            key = (entity_type, name.lower())
            entities_by_key[key] = {
                "id": "",
                "type": entity_type,
                "name": name,
                "properties": {},
            }
        return list(entities_by_key.values()), rejected

    def extract(self, document: dict[str, Any], chunk: ChunkRecord) -> dict[str, Any]:
        entities, rejected = self._extract_entities(chunk)
        if len(entities) < 2:
            return {
                "paper": _paper_payload(document, chunk),
                "entities": entities,
                "relationships": [],
                "rejected_candidates": rejected,
            }

        raw_relationships = self.language_model.generate_json(
            _relationship_prompt(document, chunk, entities),
            relationship_extraction_json_schema(),
        )
        relationships = raw_relationships.get("relationships") if isinstance(raw_relationships.get("relationships"), list) else []
        llm_rejected = raw_relationships.get("rejected_candidates")
        if isinstance(llm_rejected, list):
            for item in llm_rejected:
                if isinstance(item, dict):
                    rejected.append({"text": str(item.get("text") or ""), "reason": str(item.get("reason") or "")})

        return {
            "paper": _paper_payload(document, chunk),
            "entities": entities,
            "relationships": relationships,
            "rejected_candidates": rejected,
        }


class NoopExtractor:
    provider = "noop"

    def __init__(self, model: str = "noop-extractor-v0") -> None:
        self.model = model

    def extract(self, document: dict[str, Any], chunk: ChunkRecord) -> dict[str, Any]:
        return {
            "paper": _paper_payload(document, chunk),
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


def get_extractor(provider: str, model: str | None = None, entity_model: str | None = None) -> BiomedicalExtractor:
    normalized = provider.lower().strip()
    if normalized == "openai":
        return OpenAIResponsesExtractor(model=model)
    if normalized in {"gliner_ollama", "gliner-ollama"}:
        return GLiNEROllamaExtractor(model=model, entity_model=entity_model)
    if normalized in {"noop", "none"}:
        return NoopExtractor(model=model or "noop-extractor-v0")
    raise ValueError(f"Unsupported extractor provider: {provider}")


__all__ = [
    "BiomedicalExtractor",
    "GLiNEROllamaExtractor",
    "OpenAIResponsesExtractor",
    "NoopExtractor",
    "StaticFixtureExtractor",
    "get_extractor",
    "extraction_json_schema",
    "relationship_extraction_json_schema",
    "DEFAULT_PROMPT_VERSION",
]
