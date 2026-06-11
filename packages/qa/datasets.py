from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from packages.qa.models import QuestionRecord


@dataclass(slots=True)
class TrainingExample:
    id: str
    question: str
    answer: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_json_or_jsonl(path: Path) -> Any:
    if path.suffix.lower() == ".jsonl":
        with path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]
    return json.loads(path.read_text(encoding="utf-8"))


def question_from_mapping(item: dict[str, Any], index: int) -> QuestionRecord:
    question = item.get("question") or item.get("message") or item.get("input")
    if not isinstance(question, str) or not question.strip():
        raise ValueError(f"Question record {index} does not include a question")
    reserved = {"id", "question", "message", "input", "expected_facts", "expected_entities", "expected_relationships"}
    return QuestionRecord(
        id=str(item.get("id") or f"q{index:04d}"),
        question=question.strip(),
        expected_facts=list(item.get("expected_facts") or []),
        expected_entities=list(item.get("expected_entities") or []),
        expected_relationships=list(item.get("expected_relationships") or []),
        metadata={key: value for key, value in item.items() if key not in reserved},
    )


def read_question_file(path: Path, limit: int | None = None) -> list[QuestionRecord]:
    payload = _read_json_or_jsonl(path)
    records = payload.get("questions") if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError(f"Question file must contain a list of questions: {path}")
    questions = [question_from_mapping(item, index + 1) for index, item in enumerate(records)]
    return questions[:limit] if limit is not None else questions


def collect_questions(
    question_groups: list[list[str]] | None,
    question_file: Path | None,
    limit: int | None = None,
) -> list[QuestionRecord]:
    questions: list[QuestionRecord] = []
    if question_file is not None:
        questions.extend(read_question_file(question_file))
    for group in question_groups or []:
        for text in group:
            questions.append(QuestionRecord(id=f"q{len(questions) + 1:04d}", question=text.strip()))
    if not questions:
        raise ValueError("Provide at least one --question or --question-file")
    return questions[:limit] if limit is not None else questions


def training_example_from_mapping(item: dict[str, Any], index: int) -> TrainingExample:
    question = item.get("question") or item.get("input") or item.get("message")
    answer = item.get("answer") or item.get("expected_answer")
    if answer is None and item.get("expected_facts"):
        answer = " ".join(str(fact) for fact in item["expected_facts"])
    if not isinstance(question, str) or not question.strip():
        raise ValueError(f"Training record {index} does not include a question")
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError(f"Training record {index} does not include an answer or expected_facts")
    reserved = {"id", "question", "input", "message", "answer", "expected_answer", "expected_facts", "evidence"}
    return TrainingExample(
        id=str(item.get("id") or f"train{index:04d}"),
        question=question.strip(),
        answer=answer.strip(),
        evidence=list(item.get("evidence") or item.get("sources") or []),
        metadata={key: value for key, value in item.items() if key not in reserved},
    )


def read_training_dataset(path: Path, limit: int | None = None) -> list[TrainingExample]:
    payload = _read_json_or_jsonl(path)
    records = payload.get("examples") if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError(f"Training dataset must contain a list of examples: {path}")
    examples = [training_example_from_mapping(item, index + 1) for index, item in enumerate(records)]
    return examples[:limit] if limit is not None else examples


def to_openai_finetune_record(example: TrainingExample) -> dict[str, Any]:
    evidence_text = json.dumps(example.evidence, ensure_ascii=True)
    user_content = example.question
    if example.evidence:
        user_content = f"{example.question}\n\nRetrieved evidence:\n{evidence_text}"
    return {
        "messages": [
            {
                "role": "system",
                "content": "Answer biomedical questions using only the provided MedGraphRAG evidence.",
            },
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": example.answer},
        ]
    }


__all__ = [
    "TrainingExample",
    "collect_questions",
    "read_question_file",
    "read_training_dataset",
    "to_openai_finetune_record",
]
