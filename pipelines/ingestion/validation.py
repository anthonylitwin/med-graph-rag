from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from typing import Any

from pipelines.ingestion.models import ChunkRecord, ExtractionContext


BIOMEDICAL_ENTITY_TYPES = {"Drug", "Condition", "Symptom", "RiskFactor", "Biomarker"}
ALLOWED_ENTITY_TYPES = BIOMEDICAL_ENTITY_TYPES | {"Paper"}
ALLOWED_RELATIONSHIP_TYPES = {
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
    "MENTIONS",
}
ENTITY_PREFIXES = {
    "Drug": "drug",
    "Condition": "condition",
    "Symptom": "symptom",
    "RiskFactor": "riskfactor",
    "Biomarker": "biomarker",
    "Paper": "paper",
}


def _canonical_type(value: Any) -> str:
    raw = str(value or "").strip()
    for allowed in ALLOWED_ENTITY_TYPES:
        if raw.lower() == allowed.lower():
            return allowed
    return raw


def normalize_name(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return re.sub(r"_+", "_", normalized)


def normalize_entity_id(entity_type: str, name: str) -> str:
    canonical = _canonical_type(entity_type)
    prefix = ENTITY_PREFIXES.get(canonical)
    if prefix is None:
        raise ValueError(f"Unsupported entity type: {entity_type}")
    return f"{prefix}:{normalize_name(name)}"


def relationship_id(
    source_id: str,
    relationship_type: str,
    target_id: str,
    pmcid: str,
    chunk_id: str,
    evidence: str,
) -> str:
    payload = "|".join([source_id, relationship_type, target_id, pmcid, chunk_id, evidence])
    return f"rel:{hashlib.sha1(payload.encode('utf-8')).hexdigest()}"


def mention_relationship_id(paper_id: str, entity_id: str, pmcid: str) -> str:
    payload = "|".join([paper_id, "MENTIONS", entity_id, pmcid])
    return f"rel:{hashlib.sha1(payload.encode('utf-8')).hexdigest()}"


def _direction_is_valid(relationship_type: str, source_type: str, target_type: str) -> bool:
    if relationship_type == "ASSOCIATED_WITH":
        return source_type in BIOMEDICAL_ENTITY_TYPES and target_type in BIOMEDICAL_ENTITY_TYPES
    rules = {
        "TREATS": {("Drug", "Condition")},
        "PREVENTS": {("Drug", "Condition")},
        "REDUCES": {("Drug", "Biomarker")},
        "INCREASES": {("Drug", "Biomarker")},
        "HAS_ADVERSE_EFFECT": {("Drug", "Condition")},
        "CAUSES": {("Condition", "Condition")},
        "HAS_SYMPTOM": {("Condition", "Symptom")},
        "INCREASES_RISK_OF": {("RiskFactor", "Condition")},
        "INTERACTS_WITH": {("Drug", "Drug")},
        "CONTRAINDICATED_FOR": {("Drug", "Condition")},
        "MENTIONS": {("Paper", "Drug"), ("Paper", "Condition"), ("Paper", "Symptom"), ("Paper", "RiskFactor"), ("Paper", "Biomarker")},
    }
    return (source_type, target_type) in rules.get(relationship_type, set())


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _reject(rejected: list[dict[str, str]], text: str, reason: str) -> None:
    rejected.append({"text": str(text), "reason": reason})


def _normalize_entity(raw_entity: dict[str, Any], context: ExtractionContext) -> dict[str, Any] | None:
    entity_type = _canonical_type(raw_entity.get("type"))
    name = str(raw_entity.get("name") or "").strip()
    if entity_type not in BIOMEDICAL_ENTITY_TYPES or not name:
        return None

    entity_id = normalize_entity_id(entity_type, name)
    properties = deepcopy(raw_entity.get("properties") if isinstance(raw_entity.get("properties"), dict) else {})
    properties.update(
        {
            "source": properties.get("source") or "pmc",
            "extractor": context.extractor,
            "model": context.model,
            "created_at": context.created_at,
        }
    )
    return {"id": entity_id, "type": entity_type, "name": name, "properties": properties}


def _normalize_endpoint(endpoint: dict[str, Any], document: dict[str, Any], context: ExtractionContext) -> dict[str, Any] | None:
    endpoint_type = _canonical_type(endpoint.get("type"))
    endpoint_name = str(endpoint.get("name") or "").strip()
    if endpoint_type == "Paper":
        return {
            "id": str(document["id"]),
            "type": "Paper",
            "name": str(document.get("title") or endpoint_name or document["id"]),
        }
    if endpoint_type not in BIOMEDICAL_ENTITY_TYPES or not endpoint_name:
        return None
    return {
        "id": normalize_entity_id(endpoint_type, endpoint_name),
        "type": endpoint_type,
        "name": endpoint_name,
    }


def validate_extraction_output(
    raw_output: dict[str, Any],
    document: dict[str, Any],
    chunk: ChunkRecord,
    context: ExtractionContext,
) -> dict[str, Any]:
    if not isinstance(raw_output, dict):
        raise ValueError("Extraction output must be a JSON object")

    entities_by_id: dict[str, dict[str, Any]] = {}
    relationships_by_id: dict[str, dict[str, Any]] = {}
    rejected: list[dict[str, str]] = []

    for raw_entity in _as_list(raw_output.get("entities")):
        if not isinstance(raw_entity, dict):
            _reject(rejected, raw_entity, "entity is not an object")
            continue
        entity = _normalize_entity(raw_entity, context)
        if entity is None:
            _reject(rejected, raw_entity, "entity has unsupported type or missing name")
            continue
        entities_by_id[entity["id"]] = entity

    for raw_relationship in _as_list(raw_output.get("relationships")):
        if not isinstance(raw_relationship, dict):
            _reject(rejected, raw_relationship, "relationship is not an object")
            continue

        relationship_type = str(raw_relationship.get("type") or "").strip().upper()
        if relationship_type not in ALLOWED_RELATIONSHIP_TYPES:
            _reject(rejected, raw_relationship, "relationship type is not in the ontology")
            continue

        source = _normalize_endpoint(
            raw_relationship.get("source") if isinstance(raw_relationship.get("source"), dict) else {},
            document,
            context,
        )
        target = _normalize_endpoint(
            raw_relationship.get("target") if isinstance(raw_relationship.get("target"), dict) else {},
            document,
            context,
        )
        if source is None or target is None:
            _reject(rejected, raw_relationship, "relationship endpoint is invalid")
            continue
        if not _direction_is_valid(relationship_type, source["type"], target["type"]):
            _reject(rejected, raw_relationship, "relationship direction is invalid for the ontology")
            continue

        raw_properties = raw_relationship.get("properties") if isinstance(raw_relationship.get("properties"), dict) else {}
        evidence = str(raw_properties.get("evidence") or "").strip()
        try:
            confidence = float(raw_properties.get("confidence"))
        except (TypeError, ValueError):
            _reject(rejected, raw_relationship, "relationship confidence is missing or invalid")
            continue
        if not evidence:
            _reject(rejected, raw_relationship, "relationship evidence is required")
            continue
        if confidence < context.min_confidence or confidence > 1:
            _reject(rejected, raw_relationship, "relationship confidence is outside the accepted range")
            continue

        for endpoint in (source, target):
            if endpoint["type"] in BIOMEDICAL_ENTITY_TYPES and endpoint["id"] not in entities_by_id:
                entities_by_id[endpoint["id"]] = {
                    "id": endpoint["id"],
                    "type": endpoint["type"],
                    "name": endpoint["name"],
                    "properties": {
                        "source": "pmc",
                        "extractor": context.extractor,
                        "model": context.model,
                        "created_at": context.created_at,
                    },
                }

        rel_id = relationship_id(
            source_id=source["id"],
            relationship_type=relationship_type,
            target_id=target["id"],
            pmcid=str(document.get("pmcid") or chunk.pmcid),
            chunk_id=chunk.id,
            evidence=evidence,
        )
        relationships_by_id[rel_id] = {
            "id": rel_id,
            "type": relationship_type,
            "source": source,
            "target": target,
            "properties": {
                **raw_properties,
                "confidence": confidence,
                "evidence": evidence,
                "source_pmid": str(document.get("pmid") or raw_properties.get("source_pmid") or ""),
                "source_pmcid": str(document.get("pmcid") or raw_properties.get("source_pmcid") or chunk.pmcid),
                "chunk_id": chunk.id,
                "extractor": context.extractor,
                "model": context.model,
                "prompt_version": context.prompt_version,
                "created_at": context.created_at,
            },
        }

    for raw_rejected in _as_list(raw_output.get("rejected_candidates")):
        if isinstance(raw_rejected, dict):
            _reject(rejected, raw_rejected.get("text", ""), str(raw_rejected.get("reason", "")))

    return {
        "paper": {
            "pmid": str(document.get("pmid") or ""),
            "pmcid": str(document.get("pmcid") or chunk.pmcid),
            "title": str(document.get("title") or ""),
            "year": str(document.get("year") or ""),
            "journal": str(document.get("journal") or ""),
            "doi": str(document.get("doi") or ""),
            "authors": document.get("authors") if isinstance(document.get("authors"), list) else [],
            "abstract": str(document.get("abstract") or ""),
        },
        "entities": list(entities_by_id.values()),
        "relationships": list(relationships_by_id.values()),
        "rejected_candidates": rejected,
    }
