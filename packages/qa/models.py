from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from packages.llm.models import DEFAULT_FRONTIER_MODEL
from packages.llm.profiles import DEFAULT_MODEL_PROFILE


DEFAULT_QA_OUTPUT_ROOT = Path("data/qa/qa_v001")
DEFAULT_QA_PROVIDER = "openai"
DEFAULT_QA_RETRIEVER = "graph"
DEFAULT_QA_PROMPT_VERSION = "001_qa_prompt"
DEFAULT_MAX_EVIDENCE = 12


@dataclass(slots=True)
class QuestionRecord:
    id: str
    question: str
    expected_facts: list[str] = field(default_factory=list)
    expected_entities: list[str] = field(default_factory=list)
    expected_relationships: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RetrievedEvidence:
    id: str
    source_name: str
    source_labels: list[str]
    relationship_type: str
    target_name: str
    target_labels: list[str]
    evidence_text: str = ""
    confidence: float | None = None
    source_pmcid: str = ""
    source_pmid: str = ""
    chunk_id: str = ""
    document_id: str = ""
    document_title: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "sourceName": self.source_name,
            "sourceLabels": self.source_labels,
            "relationshipType": self.relationship_type,
            "targetName": self.target_name,
            "targetLabels": self.target_labels,
            "evidenceText": self.evidence_text,
            "confidence": self.confidence,
            "sourcePmcid": self.source_pmcid,
            "sourcePmid": self.source_pmid,
            "chunkId": self.chunk_id,
            "documentId": self.document_id,
            "title": self.document_title,
        }


@dataclass(slots=True)
class AnswerRecord:
    id: str
    question: str
    answer: str
    sources: list[dict[str, Any]]
    reasoning_path: list[dict[str, Any]]
    model: str
    provider: str
    retriever: str
    retrieved_evidence: list[dict[str, Any]]
    confidence: float = 0.0
    abstained: bool = False
    prompt_version: str = DEFAULT_QA_PROMPT_VERSION
    raw_response: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
            "answer": self.answer,
            "sources": self.sources,
            "reasoningPath": self.reasoning_path,
            "model": self.model,
            "provider": self.provider,
            "retriever": self.retriever,
            "retrievedEvidence": self.retrieved_evidence,
            "confidence": self.confidence,
            "abstained": self.abstained,
            "promptVersion": self.prompt_version,
            "rawResponse": self.raw_response,
        }


@dataclass(slots=True)
class QAConfig:
    questions: list[QuestionRecord]
    output_root: Path = DEFAULT_QA_OUTPUT_ROOT
    clean_output: bool = False
    model_profile: str = DEFAULT_MODEL_PROFILE
    answerer_provider: str = DEFAULT_QA_PROVIDER
    model: str = DEFAULT_FRONTIER_MODEL
    retriever: str = DEFAULT_QA_RETRIEVER
    max_evidence: int = DEFAULT_MAX_EVIDENCE
    skip_answer: bool = False
    fail_fast: bool = False
    limit: int | None = None


@dataclass(slots=True)
class QAPipelineResult:
    question_id: str
    question: str
    answer_path: Path
    retrieved_path: Path
    model_profile: str
    provider: str
    model: str
    retriever: str
    retrieved_count: int = 0
    source_count: int = 0
    confidence: float = 0.0
    abstained: bool = False
    answer_status: str = "pending"
    status: str = "pending"
    error: str = ""

    def manifest_row(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "question": self.question,
            "answer_path": self.answer_path.as_posix(),
            "retrieved_path": self.retrieved_path.as_posix(),
            "model_profile": self.model_profile,
            "provider": self.provider,
            "model": self.model,
            "retriever": self.retriever,
            "retrieved_count": self.retrieved_count,
            "source_count": self.source_count,
            "confidence": self.confidence,
            "abstained": self.abstained,
            "answer_status": self.answer_status,
            "status": self.status,
            "error": self.error,
        }
