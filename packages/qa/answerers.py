from __future__ import annotations

from typing import Any

from packages.llm.providers import LanguageModel
from packages.qa.models import AnswerRecord, DEFAULT_QA_PROMPT_VERSION, QuestionRecord, RetrievedEvidence
from packages.qa.prompts import format_qa_prompt, qa_answer_json_schema
from packages.qa.retrievers import EvidenceRetriever


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
    if relationship == "DEFINITION_OF":
        return f"{source}: {target}"
    return f"{source} is connected to {target} by {relationship}."


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
    evidence_answer = " ".join(_relationship_to_sentence(item) for item in evidence)
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
        evidence = self.retriever.retrieve(question.question, self.max_evidence)
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

        sources = raw.get("sources") if isinstance(raw.get("sources"), list) and raw.get("sources") else _sources_from_evidence(evidence)
        reasoning_path = (
            raw.get("reasoningPath")
            if isinstance(raw.get("reasoningPath"), list) and raw.get("reasoningPath")
            else _reasoning_from_evidence(evidence)
        )
        return AnswerRecord(
            id=question.id,
            question=question.question,
            answer=str(raw.get("answer") or ""),
            sources=sources,
            reasoning_path=reasoning_path,
            model=self.model.model,
            provider=self.model.provider,
            retriever=self.retriever.name,
            retrieved_evidence=evidence_payload,
            confidence=_confidence(raw.get("confidence")),
            abstained=bool(raw.get("abstained")),
            prompt_version=self.prompt_version,
            raw_response=raw,
        )


__all__ = ["GraphRAGAnswerer"]
