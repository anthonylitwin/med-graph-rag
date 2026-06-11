from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from typing import Any

from packages.llm.providers import get_language_model
from packages.qa.answerers import GraphRAGAnswerer
from packages.qa.models import QAConfig, QAPipelineResult
from packages.qa.retrievers import get_retriever


MANIFEST_FIELDNAMES = [
    "question_id",
    "question",
    "answer_path",
    "retrieved_path",
    "provider",
    "model",
    "retriever",
    "retrieved_count",
    "source_count",
    "confidence",
    "abstained",
    "answer_status",
    "status",
    "error",
]


def ensure_output_directories(output_root: Path, clean_output: bool = False) -> tuple[Path, Path]:
    retrieved_dir = output_root / "retrieved"
    answers_dir = output_root / "answers"
    if clean_output and output_root.exists():
        shutil.rmtree(output_root)
    retrieved_dir.mkdir(parents=True, exist_ok=True)
    answers_dir.mkdir(parents=True, exist_ok=True)
    return retrieved_dir, answers_dir


def _write_manifest(output_root: Path, results: list[QAPipelineResult]) -> None:
    manifest_path = output_root / "manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDNAMES)
        writer.writeheader()
        writer.writerows([result.manifest_row() for result in results])


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def process_questions(config: QAConfig) -> list[QAPipelineResult]:
    questions = config.questions[: config.limit] if config.limit is not None else config.questions
    retrieved_dir, answers_dir = ensure_output_directories(config.output_root, config.clean_output)
    retriever = get_retriever(config.retriever)
    model = get_language_model(config.answerer_provider, config.model)
    answerer = GraphRAGAnswerer(model=model, retriever=retriever, max_evidence=config.max_evidence)
    results: list[QAPipelineResult] = []

    for question in questions:
        retrieved_path = retrieved_dir / f"{question.id}.json"
        answer_path = answers_dir / f"{question.id}.json"
        result = QAPipelineResult(
            question_id=question.id,
            question=question.question,
            answer_path=answer_path,
            retrieved_path=retrieved_path,
            provider=model.provider,
            model=model.model,
            retriever=retriever.name,
        )
        try:
            if config.skip_answer:
                evidence = retriever.retrieve(question.question, config.max_evidence)
                retrieved_payload = {
                    "question": question.to_dict(),
                    "retrievedEvidence": [item.to_dict() for item in evidence],
                }
                _write_json(retrieved_path, retrieved_payload)
                result.retrieved_count = len(evidence)
                result.answer_status = "skipped"
                result.status = "ok"
            else:
                answer = answerer.answer(question)
                retrieved_payload = {
                    "question": question.to_dict(),
                    "retrievedEvidence": answer.retrieved_evidence,
                }
                _write_json(retrieved_path, retrieved_payload)
                _write_json(answer_path, answer.to_dict())
                result.retrieved_count = len(answer.retrieved_evidence)
                result.source_count = len(answer.sources)
                result.confidence = answer.confidence
                result.abstained = answer.abstained
                result.answer_status = "ok"
                result.status = "ok"
        except Exception as exc:  # noqa: BLE001
            result.error = str(exc)
            result.answer_status = "error"
            result.status = "error"
            if config.fail_fast:
                results.append(result)
                _write_manifest(config.output_root, results)
                raise

        results.append(result)
        _write_manifest(config.output_root, results)

    return results
