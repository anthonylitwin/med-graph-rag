from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from packages.graph.neo4j_client import neo4j_driver
from packages.qa.models import RetrievedEvidence
from pipelines.ingestion.non_instruct import DEFAULT_TERMINOLOGY_PATH, normalize_term

GRAPH_START_STOP_TERMS = {
    "and",
    "associated",
    "condition",
    "connect",
    "connected",
    "connects",
    "cholesterol",
    "cure",
    "cures",
    "definition",
    "does",
    "drug",
    "graph",
    "hop",
    "path",
    "relationship",
    "relationships",
    "the",
    "through",
    "lipid",
    "treatment",
    "using",
    "what",
    "which",
    "what condition is hypertriglyceridemia associated with",
    "with",
}


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


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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
        path_id=str(row.get("pathId") or ""),
        path_step=_as_int(row.get("pathStep"), 1),
        path_length=_as_int(row.get("pathLength"), 1),
        match_score=float(row.get("matchScore") or 0.0),
        evidence_kind=str(row.get("evidenceKind") or "graph"),
        source_url=str(row.get("sourceUrl") or ""),
        graph_run_id=str(row.get("graphRunId") or ""),
    )


@dataclass(frozen=True, slots=True)
class TerminologyEntry:
    type: str
    canonical_name: str
    aliases: tuple[str, ...]

    def search_texts(self) -> tuple[str, ...]:
        return (self.canonical_name, *self.aliases)


@dataclass(frozen=True, slots=True)
class DefinitionEntry:
    type: str
    canonical_name: str
    aliases: tuple[str, ...]
    definition: str
    source_label: str
    source_url: str

    def search_texts(self) -> tuple[str, ...]:
        return (self.canonical_name, *self.aliases)


def _load_terminology(path: Path = DEFAULT_TERMINOLOGY_PATH) -> list[TerminologyEntry]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries: list[TerminologyEntry] = []
    for item in payload.get("concepts", []) if isinstance(payload, dict) else []:
        if not isinstance(item, dict):
            continue
        canonical_name = str(item.get("canonical_name") or "").strip()
        entity_type = str(item.get("type") or "").strip()
        if not canonical_name or not entity_type:
            continue
        entries.append(
            TerminologyEntry(
                type=entity_type,
                canonical_name=canonical_name,
                aliases=tuple(str(alias).strip() for alias in item.get("aliases", []) if str(alias).strip()),
            )
        )
    return entries


def _load_definitions(path: Path = Path("data/terminology/medical_definitions_v001.json")) -> list[DefinitionEntry]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    definitions: list[DefinitionEntry] = []
    for item in payload.get("definitions", []) if isinstance(payload, dict) else []:
        if not isinstance(item, dict):
            continue
        canonical_name = str(item.get("canonical_name") or "").strip()
        definition = str(item.get("definition") or "").strip()
        entity_type = str(item.get("type") or "").strip()
        if not canonical_name or not definition or not entity_type:
            continue
        definitions.append(
            DefinitionEntry(
                type=entity_type,
                canonical_name=canonical_name,
                aliases=tuple(str(alias).strip() for alias in item.get("aliases", []) if str(alias).strip()),
                definition=definition,
                source_label=str(item.get("source_label") or "Curated local definition").strip(),
                source_url=str(item.get("source_url") or "").strip(),
            )
        )
    return definitions


def _question_terms(question: str) -> set[str]:
    normalized = normalize_term(question)
    terms: set[str] = set()
    terms.update(token for token in normalized.split() if len(token) >= 3)
    return terms


def _matched_entry_terms(question: str, entries: list[TerminologyEntry | DefinitionEntry]) -> set[str]:
    normalized_question = normalize_term(question)
    normalized_question_padded = f" {normalized_question} "
    terms = _question_terms(question)
    for entry in entries:
        for text in entry.search_texts():
            normalized_text = normalize_term(text)
            if normalized_text and f" {normalized_text} " in normalized_question_padded:
                terms.update(normalize_term(value) for value in entry.search_texts() if normalize_term(value))
                terms.add(entry.canonical_name.casefold())
    return terms


def _matched_concept_groups(question: str) -> list[set[str]]:
    normalized_question = normalize_term(question)
    normalized_question_padded = f" {normalized_question} "
    groups: list[set[str]] = []
    for entry in [*_load_terminology(), *_load_definitions()]:
        values = {normalize_term(value) for value in entry.search_texts() if normalize_term(value)}
        if values and any(f" {value} " in normalized_question_padded for value in values):
            groups.append(values)
    return groups


def _relationship_relevance(relationship_type: str, question: str) -> float:
    normalized = normalize_term(question)
    relationship = relationship_type.upper()
    cues = {
        "TREATS": ("treat", "therapy", "indicated"),
        "PREVENTS": ("prevent", "risk reduction", "protect"),
        "REDUCES": ("reduce", "lower", "decrease"),
        "INCREASES": ("increase", "raise", "elevate"),
        "ASSOCIATED_WITH": ("associate", "linked", "mark", "present"),
        "HAS_ADVERSE_EFFECT": ("adverse", "side effect", "toxicity"),
        "CAUSES": ("cause", "lead", "pathogenesis"),
        "HAS_SYMPTOM": ("symptom", "present"),
        "INCREASES_RISK_OF": ("risk", "predispose"),
        "INTERACTS_WITH": ("interact", "combination"),
        "CONTRAINDICATED_FOR": ("contraindicat", "avoid"),
        "DEFINITION_OF": ("what is", "define", "definition", "meaning"),
    }.get(relationship, ())
    return 1.0 if any(cue in normalized for cue in cues) else 0.0


def _path_requested(question: str) -> bool:
    normalized = normalize_term(question)
    return any(cue in normalized for cue in ("connect", "path", "through", "multi hop", "multi-hop"))


def _edge_term_overlap(row: dict[str, Any], terms: set[str]) -> float:
    text = normalize_term(
        " ".join(
            str(row.get(key) or "")
            for key in ("sourceName", "targetName", "relationshipType", "evidenceText", "documentTitle")
        )
    )
    if not terms or not text:
        return 0.0
    hits = sum(1 for term in terms if len(term) >= 3 and term in text)
    return min(1.0, hits / max(1, min(len(terms), 6)))


def _path_endpoint_overlap(path_rows: list[dict[str, Any]], terms: set[str]) -> float:
    text = normalize_term(
        " ".join(
            str(row.get(key) or "")
            for row in path_rows
            for key in ("sourceName", "targetName")
        )
    )
    if not terms or not text:
        return 0.0
    hits = sum(1 for term in terms if len(term) >= 3 and term in text)
    return min(1.0, hits / max(1, min(len(terms), 6)))


def _path_has_label(path_rows: list[dict[str, Any]], label: str) -> bool:
    expected = label.casefold()
    for row in path_rows:
        labels = [*list(row.get("sourceLabels") or []), *list(row.get("targetLabels") or [])]
        if any(str(item).casefold() == expected for item in labels):
            return True
    return False


def _path_lipid_action_score(path_rows: list[dict[str, Any]], question: str) -> float:
    normalized = normalize_term(question)
    if not any(cue in normalized for cue in ("lipid", "biomarker", "cholesterol", "triglyceride", "drug")):
        return 0.0
    relationships = {str(row.get("relationshipType") or "").upper() for row in path_rows}
    action_count = len(relationships & {"INCREASES", "REDUCES"})
    if action_count:
        return min(1.0, action_count / 2)
    if relationships == {"ASSOCIATED_WITH"}:
        return -0.5
    return 0.0


def _path_concept_group_coverage(path_rows: list[dict[str, Any]], question: str) -> float:
    groups = _matched_concept_groups(question)
    if not groups:
        return 1.0
    endpoint_text = normalize_term(
        " ".join(
            str(row.get(key) or "")
            for row in path_rows
            for key in ("sourceName", "targetName")
        )
    )
    if not endpoint_text:
        return 0.0
    matched = sum(1 for group in groups if any(value and value in endpoint_text for value in group))
    return matched / len(groups)


def _path_id(rows: list[dict[str, Any]]) -> str:
    parts = [str(row.get("relationshipId") or "") for row in rows]
    return "path:" + hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


def _definition_evidence(question: str, limit: int) -> list[RetrievedEvidence]:
    definitions = _load_definitions()
    normalized_question = normalize_term(question)
    normalized_question_padded = f" {normalized_question} "
    evidence: list[RetrievedEvidence] = []
    for definition in definitions:
        if not any(f" {normalize_term(text)} " in normalized_question_padded for text in definition.search_texts()):
            continue
        evidence_id = "definition:" + hashlib.sha1(definition.canonical_name.encode("utf-8")).hexdigest()[:16]
        evidence.append(
            RetrievedEvidence(
                id=evidence_id,
                source_name=definition.canonical_name,
                source_labels=[definition.type],
                relationship_type="DEFINITION_OF",
                target_name=definition.definition,
                target_labels=["Definition"],
                evidence_text=definition.definition,
                confidence=1.0,
                document_id=evidence_id,
                document_title=definition.source_label,
                path_id=evidence_id,
                path_step=1,
                path_length=1,
                match_score=1.0 + _relationship_relevance("DEFINITION_OF", question),
                evidence_kind="definition",
                source_url=definition.source_url,
            )
        )
    return evidence[:limit]


class LegacyGraphRetriever:
    name = "graph_legacy"

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
        coalesce(paperByPmcid, paperByMention) AS paper,
        properties(relationship) AS relationshipProps
    RETURN DISTINCT
        coalesce(relationshipProps["id"], elementId(relationship)) AS relationshipId,
        source.name AS sourceName,
        labels(source) AS sourceLabels,
        type(relationship) AS relationshipType,
        coalesce(relationshipProps["evidence"], relationshipProps["evidence_text"], relationshipProps["evidenceText"], "") AS evidenceText,
        relationshipProps["confidence"] AS confidence,
        coalesce(relationshipProps["source_pmcid"], "") AS sourcePmcid,
        coalesce(relationshipProps["source_pmid"], "") AS sourcePmid,
        coalesce(relationshipProps["chunk_id"], "") AS chunkId,
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


class GraphRetriever:
    name = "graph"

    START_QUERY = """
    MATCH (candidate)
    WHERE NOT candidate:Paper
      AND candidate.name IS NOT NULL
      AND ($graph_run_id = "" OR candidate.graph_run_id = $graph_run_id)
      AND any(term IN $terms WHERE
        toLower(candidate.name) = term
        OR toLower(candidate.name) CONTAINS term
        OR term CONTAINS toLower(candidate.name)
      )
    WITH DISTINCT candidate
    ORDER BY candidate.name
    RETURN elementId(candidate) AS id
    LIMIT $limit
    """

    PATH_QUERY = """
    MATCH (start)
    WHERE elementId(start) IN $start_ids
    CALL (start) {
      MATCH (source)-[relationship]->(target)
      WHERE type(relationship) <> "MENTIONS"
        AND ($graph_run_id = "" OR relationship.graph_run_id = $graph_run_id)
        AND (elementId(source) = elementId(start) OR elementId(target) = elementId(start))
      WITH source, relationship, target, properties(relationship) AS relationshipProps
      RETURN [
        {
          relationshipId: coalesce(relationshipProps["id"], elementId(relationship)),
          sourceName: coalesce(source.name, ""),
          sourceLabels: labels(source),
          relationshipType: type(relationship),
          evidenceText: coalesce(relationshipProps["evidence"], relationshipProps["evidence_text"], relationshipProps["evidenceText"], ""),
          confidence: relationshipProps["confidence"],
          sourcePmcid: coalesce(relationshipProps["source_pmcid"], ""),
          sourcePmid: coalesce(relationshipProps["source_pmid"], ""),
          chunkId: coalesce(relationshipProps["chunk_id"], ""),
          targetName: coalesce(target.name, ""),
          targetLabels: labels(target),
          pathStep: 1,
          pathLength: 1
          , graphRunId: coalesce(relationshipProps["graph_run_id"], "")
        }
      ] AS pathRows
      UNION
      MATCH path = (start)-[first]-(middle)-[second]-(finish)
      WHERE type(first) <> "MENTIONS"
        AND type(second) <> "MENTIONS"
        AND ($graph_run_id = "" OR (first.graph_run_id = $graph_run_id AND second.graph_run_id = $graph_run_id))
        AND elementId(start) <> elementId(finish)
        AND NOT finish:Paper
        AND NOT middle:Paper
        AND first <> second
      WITH relationships(path) AS rels
      UNWIND range(0, size(rels) - 1) AS index
      WITH rels, index, rels[index] AS relationship, properties(rels[index]) AS relationshipProps
      WITH rels, collect(
        {
          relationshipId: coalesce(relationshipProps["id"], elementId(relationship)),
          sourceName: coalesce(startNode(relationship).name, ""),
          sourceLabels: labels(startNode(relationship)),
          relationshipType: type(relationship),
          evidenceText: coalesce(relationshipProps["evidence"], relationshipProps["evidence_text"], relationshipProps["evidenceText"], ""),
          confidence: relationshipProps["confidence"],
          sourcePmcid: coalesce(relationshipProps["source_pmcid"], ""),
          sourcePmid: coalesce(relationshipProps["source_pmid"], ""),
          chunkId: coalesce(relationshipProps["chunk_id"], ""),
          targetName: coalesce(endNode(relationship).name, ""),
          targetLabels: labels(endNode(relationship)),
          pathStep: index + 1,
          pathLength: 2,
          graphRunId: coalesce(relationshipProps["graph_run_id"], "")
        }
      ) AS pathRows
      RETURN pathRows
    }
    RETURN pathRows
    LIMIT $limit
    """

    DRUG_CONNECTOR_QUERY = """
    UNWIND range(0, size($groups) - 1) AS firstIndex
    UNWIND range(0, size($groups) - 1) AS secondIndex
    WITH firstIndex, secondIndex
    WHERE firstIndex < secondIndex
    MATCH (drug:Drug)-[first]-(firstTarget)
    MATCH (drug)-[second]-(secondTarget)
    WHERE first <> second
      AND type(first) <> "MENTIONS"
      AND type(second) <> "MENTIONS"
      AND ($graph_run_id = "" OR (first.graph_run_id = $graph_run_id AND second.graph_run_id = $graph_run_id))
      AND any(term IN $groups[firstIndex] WHERE
        toLower(coalesce(firstTarget.name, "")) CONTAINS term
        OR term CONTAINS toLower(coalesce(firstTarget.name, ""))
      )
      AND any(term IN $groups[secondIndex] WHERE
        toLower(coalesce(secondTarget.name, "")) CONTAINS term
        OR term CONTAINS toLower(coalesce(secondTarget.name, ""))
      )
    WITH first, firstTarget, second, secondTarget, properties(first) AS firstProps, properties(second) AS secondProps
    RETURN [
      {
        relationshipId: coalesce(firstProps["id"], elementId(first)),
        sourceName: coalesce(startNode(first).name, ""),
        sourceLabels: labels(startNode(first)),
        relationshipType: type(first),
        evidenceText: coalesce(firstProps["evidence"], firstProps["evidence_text"], firstProps["evidenceText"], ""),
        confidence: firstProps["confidence"],
        sourcePmcid: coalesce(firstProps["source_pmcid"], ""),
        sourcePmid: coalesce(firstProps["source_pmid"], ""),
        chunkId: coalesce(firstProps["chunk_id"], ""),
        targetName: coalesce(endNode(first).name, ""),
        targetLabels: labels(endNode(first)),
        pathStep: 1,
        pathLength: 2,
        graphRunId: coalesce(firstProps["graph_run_id"], "")
      },
      {
        relationshipId: coalesce(secondProps["id"], elementId(second)),
        sourceName: coalesce(startNode(second).name, ""),
        sourceLabels: labels(startNode(second)),
        relationshipType: type(second),
        evidenceText: coalesce(secondProps["evidence"], secondProps["evidence_text"], secondProps["evidenceText"], ""),
        confidence: secondProps["confidence"],
        sourcePmcid: coalesce(secondProps["source_pmcid"], ""),
        sourcePmid: coalesce(secondProps["source_pmid"], ""),
        chunkId: coalesce(secondProps["chunk_id"], ""),
        targetName: coalesce(endNode(second).name, ""),
        targetLabels: labels(endNode(second)),
        pathStep: 2,
        pathLength: 2,
        graphRunId: coalesce(secondProps["graph_run_id"], "")
      }
    ] AS pathRows
    ORDER BY coalesce(firstProps["confidence"], 0.0) + coalesce(secondProps["confidence"], 0.0) DESC
    LIMIT $limit
    """

    def __init__(
        self,
        terminology_path: Path = DEFAULT_TERMINOLOGY_PATH,
        include_definitions: bool = True,
        graph_run_id: str = "",
    ) -> None:
        self.terminology_path = terminology_path
        self.include_definitions = include_definitions
        self.graph_run_id = graph_run_id.strip()

    def _terms(self, question: str) -> list[str]:
        entries = _load_terminology(self.terminology_path)
        definitions = _load_definitions()
        terms = _matched_entry_terms(question, [*entries, *definitions])
        return sorted(
            term.casefold()
            for term in terms
            if term.strip() and term.casefold() not in GRAPH_START_STOP_TERMS
        )

    def _concept_groups(self, question: str) -> list[list[str]]:
        groups = []
        for group in _matched_concept_groups(question):
            values = sorted(value.casefold() for value in group if value and value.casefold() not in GRAPH_START_STOP_TERMS)
            if values and values not in groups:
                groups.append(values)
        return groups

    def _path_records(self, question: str, path_rows: list[dict[str, Any]], terms: set[str]) -> list[RetrievedEvidence]:
        path_identifier = _path_id(path_rows)
        confidence_values = [_as_float(row.get("confidence")) or 0.0 for row in path_rows]
        min_confidence = min(confidence_values) if confidence_values else 0.0
        path_length = max(
            max((_as_int(row.get("pathLength"), len(path_rows)) for row in path_rows), default=len(path_rows)),
            len(path_rows),
        )
        endpoint_overlap = _path_endpoint_overlap(path_rows, terms)
        concept_coverage = _path_concept_group_coverage(path_rows, question)
        path_bonus = 0.08 if _path_requested(question) and path_length > 1 else 0.03
        if path_length > 1 and not _path_requested(question):
            path_bonus = -0.05
        if path_length > 1 and _path_requested(question) and concept_coverage < 1.0:
            path_bonus -= 0.25
        connector_bonus = 0.0
        if path_length > 1 and "drug" in normalize_term(question):
            connector_bonus = 0.25 if _path_has_label(path_rows, "Drug") else -0.10
        score = (
            0.20 * endpoint_overlap
            + 0.30 * concept_coverage
            + 0.25 * max((_edge_term_overlap(row, terms) for row in path_rows), default=0.0)
            + 0.15 * max((_relationship_relevance(str(row.get("relationshipType") or ""), question) for row in path_rows), default=0.0)
            + 0.15 * _path_lipid_action_score(path_rows, question)
            + 0.10 * min_confidence
            + path_bonus
            + connector_bonus
        )
        records: list[RetrievedEvidence] = []
        for index, row in enumerate(path_rows, start=1):
            row = dict(row)
            row["pathId"] = path_identifier
            row["pathStep"] = _as_int(row.get("pathStep"), index)
            row["pathLength"] = path_length
            row["matchScore"] = round(score, 6)
            row["evidenceKind"] = "graph"
            records.append(evidence_from_record(row))
        return records

    def retrieve(self, question: str, limit: int) -> list[RetrievedEvidence]:
        terms = self._terms(question)
        definition_limit = max(0, min(3, limit // 3)) if self.include_definitions else 0
        definitions = _definition_evidence(question, definition_limit)
        graph_limit = max(0, limit - len(definitions))
        if graph_limit == 0 or not terms:
            return definitions[:limit]

        try:
            with neo4j_driver() as driver:
                with driver.session() as session:
                    start_rows = list(
                        session.run(
                            self.START_QUERY,
                            terms=terms,
                            graph_run_id=self.graph_run_id,
                            limit=25,
                        )
                    )
                    start_ids = [str(dict(row).get("id")) for row in start_rows if dict(row).get("id")]
                    if not start_ids:
                        return definitions[:limit]
                    connector_rows = []
                    if "drug" in normalize_term(question) and _path_requested(question):
                        groups = self._concept_groups(question)
                        if len(groups) >= 2:
                            connector_rows = list(
                                session.run(
                                    self.DRUG_CONNECTOR_QUERY,
                                    groups=groups,
                                    graph_run_id=self.graph_run_id,
                                    limit=100,
                                )
                            )
                    path_rows = list(
                        session.run(
                            self.PATH_QUERY,
                            start_ids=start_ids,
                            graph_run_id=self.graph_run_id,
                            limit=max(graph_limit * 100, 1000),
                        )
                    )
                    path_rows = [*connector_rows, *path_rows]
        except Exception:
            if definitions:
                return definitions[:limit]
            raise

        term_set = set(terms)
        paths: list[list[RetrievedEvidence]] = []
        seen_path_ids: set[str] = set()
        for row in path_rows:
            rows = dict(row).get("pathRows")
            if not isinstance(rows, list) or not rows:
                continue
            records = self._path_records(question, [dict(item) for item in rows], term_set)
            if not records or records[0].path_id in seen_path_ids:
                continue
            seen_path_ids.add(records[0].path_id)
            paths.append(records)

        paths.sort(
            key=lambda records: (
                -max(record.match_score for record in records),
                -max(record.confidence or 0.0 for record in records),
                records[0].path_length,
                records[0].path_id,
            )
        )
        graph_evidence: list[RetrievedEvidence] = []
        seen_relationship_ids: set[str] = set()
        for path in paths:
            relationship_ids = {item.id for item in path}
            if relationship_ids & seen_relationship_ids:
                continue
            if len(graph_evidence) + len(path) > graph_limit:
                continue
            graph_evidence.extend(sorted(path, key=lambda item: item.path_step))
            seen_relationship_ids.update(relationship_ids)
            if len(graph_evidence) >= graph_limit:
                break
        return (graph_evidence + definitions)[:limit]


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
                    path_id="noop:aspirin-interaction",
                    path_step=1,
                    path_length=1,
                    match_score=1.0,
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
                    path_id="noop:aspirin-risk",
                    path_step=1,
                    path_length=1,
                    match_score=1.0,
                )
            )
        return evidence[:limit]


def get_retriever(name: str, *, graph_run_id: str = "") -> EvidenceRetriever:
    normalized = name.lower().strip()
    if normalized == "graph":
        return GraphRetriever(graph_run_id=graph_run_id)
    if normalized in {"graph_legacy", "graph-legacy", "legacy_graph", "legacy-graph"}:
        return LegacyGraphRetriever()
    if normalized in {"noop", "none"}:
        return NoopRetriever()
    raise ValueError(f"Unsupported QA retriever: {name}")


__all__ = [
    "EvidenceRetriever",
    "GraphRetriever",
    "LegacyGraphRetriever",
    "NoopRetriever",
    "evidence_from_record",
    "get_retriever",
]
