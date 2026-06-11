from __future__ import annotations

import hashlib
from typing import Any, Protocol

from packages.graph.neo4j_client import neo4j_driver
from packages.qa.models import RetrievedEvidence


class EvidenceRetriever(Protocol):
    name: str

    def retrieve(self, question: str, limit: int) -> list[RetrievedEvidence]:
        ...


def _stable_id(*parts: str) -> str:
    return "evidence:" + hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def evidence_from_record(record: Any) -> RetrievedEvidence:
    row = dict(record)
    relationship_id = str(row.get("relationshipId") or "")
    source_name = str(row.get("sourceName") or "")
    relationship_type = str(row.get("relationshipType") or "")
    target_name = str(row.get("targetName") or "")
    evidence_id = relationship_id or _stable_id(source_name, relationship_type, target_name, str(row.get("chunkId") or ""))
    return RetrievedEvidence(
        id=evidence_id,
        source_name=source_name,
        source_labels=list(row.get("sourceLabels") or []),
        relationship_type=relationship_type,
        target_name=target_name,
        target_labels=list(row.get("targetLabels") or []),
        evidence_text=str(row.get("evidenceText") or ""),
        confidence=_as_float(row.get("confidence")),
        source_pmcid=str(row.get("sourcePmcid") or ""),
        source_pmid=str(row.get("sourcePmid") or ""),
        chunk_id=str(row.get("chunkId") or ""),
        document_id=str(row.get("documentId") or ""),
        document_title=str(row.get("documentTitle") or ""),
    )


class GraphRetriever:
    name = "graph"

    QUERY = """
    MATCH (source)-[relationship]->(target)
    WHERE type(relationship) <> "MENTIONS"
      AND (
        (source.name IS NOT NULL AND toLower($question) CONTAINS toLower(source.name))
        OR (target.name IS NOT NULL AND toLower($question) CONTAINS toLower(target.name))
      )
    OPTIONAL MATCH (paperByPmcid:Paper {pmcid: relationship.source_pmcid})
    OPTIONAL MATCH (paperByMention:Paper)-[:MENTIONS]->(source)
    WITH
        source,
        relationship,
        target,
        coalesce(paperByPmcid, paperByMention) AS paper
    RETURN DISTINCT
        coalesce(relationship.id, elementId(relationship)) AS relationshipId,
        source.name AS sourceName,
        labels(source) AS sourceLabels,
        type(relationship) AS relationshipType,
        coalesce(relationship.evidence, relationship.evidence_text, relationship.evidenceText, "") AS evidenceText,
        relationship.confidence AS confidence,
        coalesce(relationship.source_pmcid, "") AS sourcePmcid,
        coalesce(relationship.source_pmid, "") AS sourcePmid,
        coalesce(relationship.chunk_id, "") AS chunkId,
        coalesce(paper.id, "") AS documentId,
        coalesce(paper.title, "") AS documentTitle,
        target.name AS targetName,
        labels(target) AS targetLabels
    ORDER BY confidence DESC
    LIMIT $limit
    """

    def retrieve(self, question: str, limit: int) -> list[RetrievedEvidence]:
        with neo4j_driver() as driver:
            with driver.session() as session:
                rows = session.run(self.QUERY, question=question.lower(), limit=limit)
                return [evidence_from_record(row) for row in rows]


class NoopRetriever:
    name = "noop"

    def retrieve(self, question: str, limit: int) -> list[RetrievedEvidence]:
        normalized = question.lower()
        evidence: list[RetrievedEvidence] = []
        if "aspirin" in normalized and ("interact" in normalized or "medication" in normalized):
            evidence.append(
                RetrievedEvidence(
                    id="noop:aspirin-interaction",
                    source_name="Aspirin",
                    source_labels=["Drug"],
                    relationship_type="MAY_INTERACT_WITH",
                    target_name="Anticoagulant medication",
                    target_labels=["Drug"],
                    evidence_text="Aspirin may interact with anticoagulant medications.",
                    confidence=0.9,
                    document_id="sample-paper-001",
                    document_title="Sample Aspirin Interaction Abstract",
                )
            )
        if "aspirin" in normalized and ("risk" in normalized or "bleeding" in normalized):
            evidence.append(
                RetrievedEvidence(
                    id="noop:aspirin-risk",
                    source_name="Aspirin",
                    source_labels=["Drug"],
                    relationship_type="MAY_INCREASE_RISK_OF",
                    target_name="Bleeding risk",
                    target_labels=["Condition"],
                    evidence_text="Aspirin can increase bleeding risk.",
                    confidence=0.9,
                    document_id="sample-paper-001",
                    document_title="Sample Aspirin Interaction Abstract",
                )
            )
        return evidence[:limit]


def get_retriever(name: str) -> EvidenceRetriever:
    normalized = name.lower().strip()
    if normalized == "graph":
        return GraphRetriever()
    if normalized in {"noop", "none"}:
        return NoopRetriever()
    raise ValueError(f"Unsupported QA retriever: {name}")


__all__ = [
    "EvidenceRetriever",
    "GraphRetriever",
    "NoopRetriever",
    "evidence_from_record",
    "get_retriever",
]
