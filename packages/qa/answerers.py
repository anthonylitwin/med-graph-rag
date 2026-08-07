from __future__ import annotations

from typing import Any

from packages.llm.providers import LanguageModel
from packages.qa.models import AnswerRecord, DEFAULT_QA_PROMPT_VERSION, QuestionRecord, RetrievedEvidence
from packages.qa.prompts import format_qa_prompt, qa_answer_json_schema
from packages.qa.retrievers import EvidenceRetriever
from pipelines.ingestion.non_instruct import normalize_term


def _confidence(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _relationship_to_sentence(evidence: RetrievedEvidence) -> str:
    source = evidence.source_name
    target = evidence.target_name
    relationship = evidence.relationship_type
    if relationship in {"INTERACTS_WITH", "MAY_INTERACT_WITH"}:
        return f"{source} may interact with {target}."
    if relationship in {"INCREASES_RISK_OF", "MAY_INCREASE_RISK_OF"}:
        return f"{source} may increase the risk of {target}."
    if relationship in {"REDUCES", "MAY_REDUCE"}:
        return f"{source} may reduce {target}."
    if relationship in {"INCREASES", "MAY_INCREASE"}:
        return f"{source} may increase {target}."
    if relationship == "TREATS":
        return f"{source} treats {target}."
    if relationship == "PREVENTS":
        return f"{source} prevents {target}."
    if relationship == "ASSOCIATED_WITH":
        return f"{source} is associated with {target}."
    if relationship == "DEFINITION_OF":
        return f"{source}: {target}"
    return f"{source} is connected to {target} by {relationship}."


def _join_names(names: list[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return f"{', '.join(names[:-1])}, and {names[-1]}"


def _relationship_cues(relationship: str) -> tuple[str, ...]:
    return {
        "REDUCES": ("reduce", "reduces", "lower", "lowers", "decrease", "decreases"),
        "MAY_REDUCE": ("reduce", "reduces", "lower", "lowers", "decrease", "decreases"),
        "INCREASES": ("increase", "increases", "raise", "raises", "elevate", "elevates"),
        "MAY_INCREASE": ("increase", "increases", "raise", "raises", "elevate", "elevates"),
        "TREATS": ("treat", "treats"),
        "PREVENTS": ("prevent", "prevents"),
        "DEFINITION_OF": ("definition", "is"),
    }.get(relationship.upper(), (normalize_term(relationship),))


def _requested_relationships(question: str) -> set[str]:
    normalized = normalize_term(question)
    if "risk" in normalized:
        return {"INCREASES_RISK_OF", "MAY_INCREASE_RISK_OF"}
    if any(cue in normalized for cue in ("reduce", "reduces", "lower", "lowers", "decrease", "decreases")):
        return {"REDUCES", "MAY_REDUCE"}
    if any(cue in normalized for cue in ("increase", "increases", "raise", "raises", "elevate", "elevates")):
        return {"INCREASES", "MAY_INCREASE", "INCREASES_RISK_OF", "MAY_INCREASE_RISK_OF"}
    if any(cue in normalized for cue in ("interact", "interaction")):
        return {"INTERACTS_WITH", "MAY_INTERACT_WITH"}
    return set()


def _requested_target_label(question: str) -> str:
    normalized = normalize_term(question)
    if "biomarker" in normalized:
        return "biomarker"
    if "drug" in normalized or "medication" in normalized:
        return "drug"
    if "condition" in normalized or "disease" in normalized or "risk" in normalized:
        return "condition"
    return ""


def _answer_mentions_evidence(answer: str, evidence: RetrievedEvidence) -> bool:
    normalized_answer = normalize_term(answer)
    source = normalize_term(evidence.source_name)
    target = normalize_term(evidence.target_name)
    if not source or not target:
        return False
    return source in normalized_answer and target in normalized_answer and any(
        normalize_term(cue) in normalized_answer for cue in _relationship_cues(evidence.relationship_type)
    )


def _dedupe_evidence(evidence: list[RetrievedEvidence]) -> list[RetrievedEvidence]:
    deduped: list[RetrievedEvidence] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in evidence:
        key = (
            normalize_term(item.source_name),
            item.relationship_type.upper(),
            normalize_term(item.target_name),
            item.evidence_kind.casefold(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _extractive_graph_answer(question: str, evidence: list[RetrievedEvidence]) -> str:
    normalized_question = normalize_term(question)
    if "graph" not in normalized_question:
        return ""

    relationships = _requested_relationships(question)
    if not relationships:
        return ""

    target_label = _requested_target_label(question)
    candidates: list[RetrievedEvidence] = []
    for item in _dedupe_evidence(evidence):
        if item.evidence_kind.casefold() != "graph":
            continue
        if item.relationship_type.upper() not in relationships:
            continue
        if target_label and not any(label.casefold() == target_label for label in item.target_labels):
            continue
        if normalize_term(item.source_name) and normalize_term(item.source_name) not in normalized_question:
            continue
        candidates.append(item)

    if not candidates:
        return ""

    target_names = _join_names([item.target_name for item in candidates])
    source_names = _join_names(sorted({item.source_name for item in candidates}))
    relationship = candidates[0].relationship_type.upper()
    if relationship in {"REDUCES", "MAY_REDUCE"}:
        return f"In the retrieved graph, {source_names} may reduce {target_names}."
    if relationship in {"INCREASES_RISK_OF", "MAY_INCREASE_RISK_OF"}:
        return f"In the retrieved graph, {source_names} may increase the risk of {target_names}."
    if relationship in {"INCREASES", "MAY_INCREASE"}:
        return f"In the retrieved graph, {source_names} may increase {target_names}."
    if relationship in {"INTERACTS_WITH", "MAY_INTERACT_WITH"}:
        return f"In the retrieved graph, {source_names} may interact with {target_names}."
    return ""


def _definition_requested(question: str) -> bool:
    normalized = normalize_term(question)
    return any(cue in normalized for cue in ("what is", "define", "definition", "meaning"))


def _extractive_definition_answer(question: str, evidence: list[RetrievedEvidence]) -> str:
    if not _definition_requested(question):
        return ""

    definitions = [item for item in _dedupe_evidence(evidence) if item.evidence_kind.casefold() == "definition"]
    if not definitions:
        return ""

    definition = definitions[0]
    answer = _relationship_to_sentence(definition)
    graph_evidence = [
        item
        for item in _dedupe_evidence(evidence)
        if item.evidence_kind.casefold() == "graph" and item.id != definition.id
    ]
    if graph_evidence:
        answer = f"{answer} Graph evidence summary: {_relationship_to_sentence(graph_evidence[0])}"
    return answer


def _completion_required_evidence(evidence: list[RetrievedEvidence]) -> list[RetrievedEvidence]:
    required: list[RetrievedEvidence] = []
    seen: set[str] = set()
    for item in evidence[:2]:
        required.append(item)
        seen.add(item.id)
    for kind in ("definition",):
        for item in evidence:
            if item.evidence_kind.casefold() == kind and item.id not in seen:
                required.append(item)
                seen.add(item.id)
                break
    return required


def _complete_answer_with_top_evidence(answer: str, evidence: list[RetrievedEvidence]) -> tuple[str, bool]:
    missing = [item for item in _completion_required_evidence(evidence) if not _answer_mentions_evidence(answer, item)]
    if not missing:
        return answer, False
    summary = " ".join(_relationship_to_sentence(item) for item in missing)
    return f"{answer} Evidence summary: {summary}", True


def _sources_from_evidence(evidence: list[RetrievedEvidence]) -> list[dict[str, Any]]:
    return [
        {
            "documentId": item.document_id,
            "title": item.document_title,
            "evidenceText": item.evidence_text,
            "confidence": item.confidence or 0.0,
            "sourcePmcid": item.source_pmcid,
            "chunkId": item.chunk_id,
            "evidenceKind": item.evidence_kind,
            "sourceUrl": item.source_url,
        }
        for item in evidence
    ]


def _reasoning_from_evidence(evidence: list[RetrievedEvidence]) -> list[dict[str, Any]]:
    path_order: dict[str, int] = {}
    for item in evidence:
        path_key = item.path_id or item.id
        path_order.setdefault(path_key, len(path_order))

    return [
        {
            "source": item.source_name,
            "relationship": item.relationship_type,
            "target": item.target_name,
            "evidenceId": item.id,
            "sourcePmcid": item.source_pmcid,
            "chunkId": item.chunk_id,
            "pathId": item.path_id,
            "pathStep": item.path_step,
            "pathLength": item.path_length,
        }
        for index, item in sorted(
            enumerate(evidence),
            key=lambda child: (path_order[child[1].path_id or child[1].id], child[1].path_step, child[0]),
        )
    ]


def _fallback_answer_from_evidence(evidence: list[RetrievedEvidence], error: Exception) -> str:
    evidence_answer = " ".join(_relationship_to_sentence(item) for item in _dedupe_evidence(evidence))
    return (
        "The graph returned supporting evidence, but the configured language model "
        f"could not generate a narrative answer ({error}). Evidence summary: {evidence_answer}"
    )


class GraphRAGAnswerer:
    def __init__(
        self,
        model: LanguageModel,
        retriever: EvidenceRetriever,
        max_evidence: int = 12,
        prompt_version: str = DEFAULT_QA_PROMPT_VERSION,
    ) -> None:
        self.model = model
        self.retriever = retriever
        self.max_evidence = max_evidence
        self.prompt_version = prompt_version

    def answer(self, question: QuestionRecord) -> AnswerRecord:
        evidence = _dedupe_evidence(self.retriever.retrieve(question.question, self.max_evidence))
        evidence_payload = [item.to_dict() for item in evidence]
        if not evidence:
            return AnswerRecord(
                id=question.id,
                question=question.question,
                answer="I could not find supporting graph evidence for this question.",
                sources=[],
                reasoning_path=[],
                model=self.model.model,
                provider=self.model.provider,
                retriever=self.retriever.name,
                retrieved_evidence=[],
                confidence=0.0,
                abstained=True,
                prompt_version=self.prompt_version,
            )

        if self.model.provider == "noop":
            sources = _sources_from_evidence(evidence)
            reasoning_path = _reasoning_from_evidence(evidence)
            confidence_values = [item.confidence for item in evidence if item.confidence is not None]
            return AnswerRecord(
                id=question.id,
                question=question.question,
                answer=" ".join(_relationship_to_sentence(item) for item in evidence),
                sources=sources,
                reasoning_path=reasoning_path,
                model=self.model.model,
                provider=self.model.provider,
                retriever=self.retriever.name,
                retrieved_evidence=evidence_payload,
                confidence=min(confidence_values) if confidence_values else 0.0,
                abstained=False,
                prompt_version=self.prompt_version,
            )

        extractive_answer = _extractive_graph_answer(question.question, evidence)
        if extractive_answer:
            sources = _sources_from_evidence(evidence)
            reasoning_path = _reasoning_from_evidence(evidence)
            confidence_values = [item.confidence for item in evidence if item.confidence is not None]
            return AnswerRecord(
                id=question.id,
                question=question.question,
                answer=extractive_answer,
                sources=sources,
                reasoning_path=reasoning_path,
                model=self.model.model,
                provider=self.model.provider,
                retriever=self.retriever.name,
                retrieved_evidence=evidence_payload,
                confidence=min(confidence_values) if confidence_values else 0.0,
                abstained=False,
                prompt_version=self.prompt_version,
                raw_response={"status": "extractive_graph_answer"},
            )

        extractive_definition_answer = _extractive_definition_answer(question.question, evidence)
        if extractive_definition_answer:
            sources = _sources_from_evidence(evidence)
            reasoning_path = _reasoning_from_evidence(evidence)
            confidence_values = [item.confidence for item in evidence if item.confidence is not None]
            return AnswerRecord(
                id=question.id,
                question=question.question,
                answer=extractive_definition_answer,
                sources=sources,
                reasoning_path=reasoning_path,
                model=self.model.model,
                provider=self.model.provider,
                retriever=self.retriever.name,
                retrieved_evidence=evidence_payload,
                confidence=min(confidence_values) if confidence_values else 0.0,
                abstained=False,
                prompt_version=self.prompt_version,
                raw_response={"status": "extractive_definition_answer"},
            )

        try:
            raw = self.model.generate_json(format_qa_prompt(question.question, evidence), qa_answer_json_schema())
        except Exception as exc:  # noqa: BLE001 - QA should still return retrieved graph evidence.
            sources = _sources_from_evidence(evidence)
            reasoning_path = _reasoning_from_evidence(evidence)
            confidence_values = [item.confidence for item in evidence if item.confidence is not None]
            return AnswerRecord(
                id=question.id,
                question=question.question,
                answer=_fallback_answer_from_evidence(evidence, exc),
                sources=sources,
                reasoning_path=reasoning_path,
                model=self.model.model,
                provider=self.model.provider,
                retriever=self.retriever.name,
                retrieved_evidence=evidence_payload,
                confidence=min(confidence_values) if confidence_values else 0.0,
                abstained=False,
                prompt_version=self.prompt_version,
                raw_response={"status": "model_error", "error": str(exc)},
            )

        answer_text, completed_with_evidence = _complete_answer_with_top_evidence(str(raw.get("answer") or ""), evidence)
        sources = (
            _sources_from_evidence(evidence)
            if completed_with_evidence
            else raw.get("sources")
            if isinstance(raw.get("sources"), list) and raw.get("sources")
            else _sources_from_evidence(evidence)
        )
        reasoning_path = (
            _reasoning_from_evidence(evidence)
            if completed_with_evidence
            else raw.get("reasoningPath")
            if isinstance(raw.get("reasoningPath"), list) and raw.get("reasoningPath")
            else _reasoning_from_evidence(evidence)
        )
        return AnswerRecord(
            id=question.id,
            question=question.question,
            answer=answer_text,
            sources=sources,
            reasoning_path=reasoning_path,
            model=self.model.model,
            provider=self.model.provider,
            retriever=self.retriever.name,
            retrieved_evidence=evidence_payload,
            confidence=_confidence(raw.get("confidence")),
            abstained=bool(raw.get("abstained")),
            prompt_version=self.prompt_version,
            raw_response=raw | {"completedWithEvidenceSummary": completed_with_evidence},
        )


__all__ = ["GraphRAGAnswerer"]
