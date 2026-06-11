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
    if relationship == "TREATS":
        return f"{source} treats {target}."
    if relationship == "PREVENTS":
        return f"{source} prevents {target}."
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
        }
        for item in evidence
    ]


def _reasoning_from_evidence(evidence: list[RetrievedEvidence]) -> list[dict[str, Any]]:
    return [
        {
            "source": item.source_name,
            "relationship": item.relationship_type,
            "target": item.target_name,
        }
        for item in evidence
    ]


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

        raw = self.model.generate_json(format_qa_prompt(question.question, evidence), qa_answer_json_schema())
        sources = raw.get("sources") if isinstance(raw.get("sources"), list) else _sources_from_evidence(evidence)
        reasoning_path = (
            raw.get("reasoningPath") if isinstance(raw.get("reasoningPath"), list) else _reasoning_from_evidence(evidence)
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
