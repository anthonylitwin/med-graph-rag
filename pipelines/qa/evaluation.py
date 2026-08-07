from __future__ import annotations

import csv
import hashlib
import json
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from packages.llm.providers import get_language_model
from packages.llm.profiles import resolve_model_profile
from packages.qa.datasets import read_question_file
from packages.qa.models import QAConfig, QuestionRecord
from pipelines.qa.pipeline import process_questions


DEFAULT_QA_EVAL_OUTPUT_ROOT = Path("data/qa/eval_v001")
DEFAULT_QA_QUESTION_FILE = Path("eval/questions/qa_gold_v001.json")
DEFAULT_TERMINOLOGY_FILE = Path("data/terminology/biomedical_aliases_v001.json")
DEFAULT_DEFINITIONS_FILE = Path("data/terminology/medical_definitions_v001.json")


@dataclass(frozen=True)
class QAEvaluationConfig:
    question_file: Path = DEFAULT_QA_QUESTION_FILE
    output_root: Path = DEFAULT_QA_EVAL_OUTPUT_ROOT
    eval_id: str | None = None
    graph_run_id: str = ""
    graph_source: str = ""
    model_profile: str = "noop"
    answerer_provider: str | None = None
    model: str | None = None
    retriever: str | None = None
    max_evidence: int = 12
    skip_answer: bool = False
    limit: int | None = None
    force: bool = False
    fail_fast: bool = False
    llm_judge_enabled: bool = False
    llm_judge_provider: str = "openai"
    llm_judge_model: str | None = None
    mlflow: bool = False
    mlflow_tracking_uri: str = "http://127.0.0.1:5000"
    mlflow_experiment: str = "medgraphrag-qa-eval"
    mlflow_run_name: str = ""
    mlflow_log_artifacts: bool = True


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _eval_id() -> str:
    return datetime.now(UTC).strftime("qa-eval-%Y%m%d%H%M%S")


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize(value: Any) -> str:
    return " ".join(_clean(value).casefold().replace("_", " ").split())


@lru_cache(maxsize=1)
def _entity_alias_groups() -> tuple[frozenset[str], ...]:
    groups: list[frozenset[str]] = []
    for path, key in ((DEFAULT_TERMINOLOGY_FILE, "concepts"), (DEFAULT_DEFINITIONS_FILE, "definitions")):
        payload = _read_json(path)
        records = payload.get(key) if isinstance(payload, dict) else []
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            names = [_normalize(record.get("canonical_name"))]
            aliases = record.get("aliases") if isinstance(record.get("aliases"), list) else []
            names.extend(_normalize(alias) for alias in aliases)
            group = frozenset(name for name in names if name)
            if group:
                groups.append(group)
    return tuple(groups)


def _entity_alias_values(value: str) -> set[str]:
    normalized = _normalize(value)
    if not normalized:
        return set()
    values = {normalized}
    for group in _entity_alias_groups():
        if normalized in group:
            values.update(group)
    return values


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_clean(item) for item in value if _clean(item)]
    if isinstance(value, str):
        return [_clean(item) for item in value.split(";") if _clean(item)]
    return [_clean(value)] if _clean(value) else []


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return payload if isinstance(payload, dict) else {"questions": payload}


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_record(path: Path) -> dict[str, Any]:
    return {"path": path.as_posix(), "sha256": _sha256_file(path)}


def _write_artifact_manifest(eval_root: Path, artifact_paths: list[Path]) -> Path:
    records = [_artifact_record(path) for path in artifact_paths if path.exists() and path.is_file()]
    return _write_json(
        eval_root / "artifact_manifest.json",
        {
            "created_at": _now_iso(),
            "artifact_count": len(records),
            "artifacts": records,
        },
    )


def _question_metadata(question: QuestionRecord) -> dict[str, Any]:
    return question.metadata if isinstance(question.metadata, dict) else {}


def _expected_evidence_ids(question: QuestionRecord) -> list[str]:
    metadata = _question_metadata(question)
    return _as_list(
        metadata.get("expected_evidence_ids")
        or metadata.get("required_evidence_ids")
        or metadata.get("relationship_gold_ids")
        or metadata.get("related_relationship_gold_id")
    )


def _expected_chunk_ids(question: QuestionRecord) -> list[str]:
    metadata = _question_metadata(question)
    return _as_list(metadata.get("expected_chunk_ids") or metadata.get("required_chunk_ids") or metadata.get("chunk_id"))


def _is_unanswerable(question: QuestionRecord) -> bool:
    metadata = _question_metadata(question)
    value = metadata.get("unanswerable", metadata.get("expected_abstention", False))
    if isinstance(value, bool):
        return value
    return _clean(value).casefold() in {"1", "true", "yes", "y"}


def _expected_hop_count(question: QuestionRecord) -> int:
    metadata = _question_metadata(question)
    value = metadata.get("expected_hop_count") or metadata.get("hop_count")
    if value is None:
        if _is_unanswerable(question):
            return 0
        return 1 if question.expected_relationships else 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 1


def _requires_definition(question: QuestionRecord) -> bool:
    metadata = _question_metadata(question)
    value = metadata.get("requires_definition", metadata.get("requires_standard_definition", False))
    if isinstance(value, bool):
        return value
    return _clean(value).casefold() in {"1", "true", "yes", "y"}


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _read_retrieved(path: Path) -> list[dict[str, Any]]:
    payload = _read_json(path)
    evidence = payload.get("retrievedEvidence")
    return evidence if isinstance(evidence, list) else []


def _read_answer(path: Path) -> dict[str, Any]:
    return _read_json(path)


def _evidence_identity_values(evidence: dict[str, Any]) -> set[str]:
    values = {
        _clean(evidence.get("id")),
        _clean(evidence.get("chunkId")),
        _clean(evidence.get("relationshipId")),
    }
    return {item for item in values if item}


def _evidence_entity_values(evidence: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for field in ("sourceName", "targetName"):
        values.update(_entity_alias_values(_clean(evidence.get(field))))
    return values


def _evidence_relationship_values(evidence: dict[str, Any]) -> set[str]:
    return {_normalize(evidence.get("relationshipType"))} - {""}


def _evidence_path_length(evidence: dict[str, Any]) -> int:
    try:
        return int(evidence.get("pathLength") or 1)
    except (TypeError, ValueError):
        return 1


def _path_complete(evidence: list[dict[str, Any]], expected_hop_count: int) -> bool:
    if expected_hop_count <= 0:
        return not evidence
    if expected_hop_count <= 1:
        return bool(evidence)
    steps_by_path: dict[str, set[int]] = {}
    for item in evidence:
        if not isinstance(item, dict):
            continue
        path_id = _clean(item.get("pathId")) or _clean(item.get("id"))
        try:
            step = int(item.get("pathStep") or 1)
        except (TypeError, ValueError):
            step = 1
        steps_by_path.setdefault(path_id, set()).add(step)
        if _evidence_path_length(item) >= expected_hop_count and len(steps_by_path[path_id]) >= expected_hop_count:
            return True
    return False


def _definition_source_hit(evidence: list[dict[str, Any]]) -> bool:
    return any(
        isinstance(item, dict)
        and _clean(item.get("evidenceKind")).casefold() == "definition"
        and bool(_clean(item.get("evidenceText")))
        for item in evidence
    )


def _contains_all(text: str, expected_items: list[str]) -> tuple[int, int, float]:
    normalized_text = _normalize(text)
    expected = [_normalize(item) for item in expected_items if _normalize(item)]
    if not expected:
        return 0, 0, 1.0
    text_tokens = set(normalized_text.split())

    def fact_matches(item: str) -> bool:
        if item in normalized_text:
            return True
        stopwords = {"a", "an", "and", "are", "as", "is", "may", "of", "the", "to", "with"}
        tokens = {token for token in item.split() if token not in stopwords}
        return bool(tokens) and tokens <= text_tokens

    matched = sum(1 for item in expected if fact_matches(item))
    return matched, len(expected), matched / len(expected)


def _coverage(expected_items: list[str], observed_items: set[str]) -> tuple[int, int, float]:
    expected = [_normalize(item) for item in expected_items if _normalize(item)]
    if not expected:
        return 0, 0, 1.0
    matched = sum(1 for item in expected if _entity_alias_values(item) & observed_items)
    return matched, len(expected), matched / len(expected)


def _evidence_id_hit(expected_ids: list[str], evidence: list[dict[str, Any]]) -> bool:
    expected = {_clean(item) for item in expected_ids if _clean(item)}
    if not expected:
        return True
    observed: set[str] = set()
    for item in evidence:
        if isinstance(item, dict):
            observed.update(_evidence_identity_values(item))
    return bool(expected & observed)


def _safe_ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _score_question(
    question: QuestionRecord,
    manifest_row: dict[str, str],
    eval_root: Path,
) -> dict[str, Any]:
    if not manifest_row:
        return {
            "question_id": question.id,
            "question": question.question,
            "question_type": _clean(_question_metadata(question).get("question_type") or _question_metadata(question).get("category")),
            "split": _clean(_question_metadata(question).get("split")),
            "status": "error",
            "answer_status": "missing",
            "retrieved_count": 0,
            "source_count": 0,
            "hop_count": _expected_hop_count(question),
            "max_retrieved_path_length": 0,
            "path_complete": False,
            "definition_source_hit": False,
            "expected_fact_hits": 0,
            "expected_fact_total": len(question.expected_facts),
            "fact_coverage": 0.0 if question.expected_facts else 1.0,
            "entity_hits": 0,
            "entity_total": len(question.expected_entities),
            "entity_coverage": 0.0 if question.expected_entities else 1.0,
            "relationship_hits": 0,
            "relationship_total": len(question.expected_relationships),
            "relationship_coverage": 0.0 if question.expected_relationships else 1.0,
            "expected_evidence_hit": False,
            "retrieval_success": False,
            "citation_supported": False,
            "abstained": False,
            "expected_abstention": _is_unanswerable(question),
            "abstention_correct": False,
            "unsupported_answer": False,
            "llm_judge_status": "disabled",
            "llm_judge_supported": "",
            "llm_judge_score": "",
            "llm_judge_notes": "",
            "answer_success": False,
            "error": "missing manifest row",
        }
    retrieved_path = Path(manifest_row.get("retrieved_path") or "")
    answer_path = Path(manifest_row.get("answer_path") or "")

    evidence = _read_retrieved(retrieved_path)
    answer_status = manifest_row.get("answer_status", "")
    answer_payload = _read_answer(answer_path) if answer_path.exists() else {}
    answer_text = _clean(answer_payload.get("answer"))
    if answer_status == "skipped":
        abstained = not evidence
    else:
        abstained = bool(answer_payload.get("abstained")) if answer_payload else _clean(manifest_row.get("abstained")).casefold() == "true"
    sources = answer_payload.get("sources") if isinstance(answer_payload.get("sources"), list) else []

    expected_evidence_ids = _expected_evidence_ids(question)
    expected_chunk_ids = _expected_chunk_ids(question)
    expected_identity_ids = expected_evidence_ids + expected_chunk_ids
    evidence_entities: set[str] = set()
    evidence_relationships: set[str] = set()
    for item in evidence:
        if isinstance(item, dict):
            evidence_entities.update(_evidence_entity_values(item))
            evidence_relationships.update(_evidence_relationship_values(item))

    expected_hops = _expected_hop_count(question)
    max_path_length = max((_evidence_path_length(item) for item in evidence if isinstance(item, dict)), default=0)
    path_complete = _path_complete(evidence, expected_hops)
    definition_hit = _definition_source_hit(evidence)
    expected_fact_hits, expected_fact_total, fact_coverage = _contains_all(answer_text, question.expected_facts)
    entity_hits, entity_total, entity_coverage = _coverage(question.expected_entities, evidence_entities)
    relationship_hits, relationship_total, relationship_coverage = _coverage(question.expected_relationships, evidence_relationships)
    evidence_hit = _evidence_id_hit(expected_identity_ids, evidence)
    unanswerable = _is_unanswerable(question)
    retrieval_success = (
        not evidence
        if unanswerable
        else bool(evidence)
        and entity_coverage >= 1.0
        and relationship_coverage >= 1.0
        and evidence_hit
        and path_complete
        and (definition_hit if _requires_definition(question) else True)
    )
    citation_supported = bool(sources) if not unanswerable and not abstained else abstained
    unsupported_answer = bool(answer_text) and not abstained and not retrieval_success
    answer_success = False if answer_status == "skipped" else (
        abstained
        if unanswerable
        else not abstained and fact_coverage >= 1.0 and citation_supported and not unsupported_answer
    )

    return {
        "question_id": question.id,
        "question": question.question,
        "question_type": _clean(_question_metadata(question).get("question_type") or _question_metadata(question).get("category")),
        "split": _clean(_question_metadata(question).get("split")),
        "status": manifest_row.get("status", ""),
        "answer_status": answer_status,
        "retrieved_count": int(manifest_row.get("retrieved_count") or 0),
        "source_count": int(manifest_row.get("source_count") or 0),
        "hop_count": expected_hops,
        "max_retrieved_path_length": max_path_length,
        "path_complete": path_complete,
        "definition_source_hit": definition_hit,
        "expected_fact_hits": expected_fact_hits,
        "expected_fact_total": expected_fact_total,
        "fact_coverage": round(fact_coverage, 6),
        "entity_hits": entity_hits,
        "entity_total": entity_total,
        "entity_coverage": round(entity_coverage, 6),
        "relationship_hits": relationship_hits,
        "relationship_total": relationship_total,
        "relationship_coverage": round(relationship_coverage, 6),
        "expected_evidence_hit": evidence_hit,
        "retrieval_success": retrieval_success,
        "citation_supported": citation_supported,
        "abstained": abstained,
        "expected_abstention": unanswerable,
        "abstention_correct": abstained == unanswerable,
        "unsupported_answer": unsupported_answer,
        "llm_judge_status": "disabled",
        "llm_judge_supported": "",
        "llm_judge_score": "",
        "llm_judge_notes": "",
        "answer_success": answer_success,
        "error": manifest_row.get("error", ""),
    }


def _judge_schema() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": "medgraphrag_qa_judge",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "supported": {"type": "boolean"},
                "score": {"type": "number", "minimum": 0, "maximum": 1},
                "missingFacts": {"type": "array", "items": {"type": "string"}},
                "unsupportedClaims": {"type": "array", "items": {"type": "string"}},
                "notes": {"type": "string"},
            },
            "required": ["supported", "score", "missingFacts", "unsupportedClaims", "notes"],
        },
    }


def _judge_prompt(question: QuestionRecord, row: dict[str, Any], answer: dict[str, Any], evidence: list[dict[str, Any]]) -> str:
    return "\n".join(
        [
            "Judge whether the answer is supported by the retrieved biomedical graph evidence.",
            "Use the expected facts only as the grading rubric. Do not add outside medical knowledge.",
            "",
            f"Question: {question.question}",
            f"Expected facts: {json.dumps(question.expected_facts, ensure_ascii=True)}",
            f"Expected entities: {json.dumps(question.expected_entities, ensure_ascii=True)}",
            f"Expected relationships: {json.dumps(question.expected_relationships, ensure_ascii=True)}",
            f"Deterministic row: {json.dumps(row, ensure_ascii=True)}",
            f"Answer: {json.dumps(answer, ensure_ascii=True)}",
            f"Retrieved evidence: {json.dumps(evidence, ensure_ascii=True)}",
        ]
    )


def _apply_llm_judge(
    config: QAEvaluationConfig,
    questions: list[QuestionRecord],
    question_rows: list[dict[str, Any]],
    manifest_rows: dict[str, dict[str, str]],
    eval_root: Path,
) -> Path:
    report_path = eval_root / "llm_judge_report.json"
    if not config.llm_judge_enabled:
        return _write_json(
            report_path,
            {
                "created_at": _now_iso(),
                "enabled": False,
                "status": "disabled",
                "message": "LLM judge scoring is disabled; deterministic gold metrics are primary.",
            },
        )

    model = get_language_model(config.llm_judge_provider, config.llm_judge_model)
    model_call_root = eval_root / "model_calls" / "llm_judge"
    model_call_root.mkdir(parents=True, exist_ok=True)
    questions_by_id = {question.id: question for question in questions}
    judged: list[dict[str, Any]] = []
    for row in question_rows:
        question = questions_by_id[row["question_id"]]
        manifest_row = manifest_rows.get(question.id, {})
        answer_path = Path(manifest_row.get("answer_path") or "")
        retrieved_path = Path(manifest_row.get("retrieved_path") or "")
        answer = _read_answer(answer_path) if answer_path.exists() else {}
        evidence = _read_retrieved(retrieved_path) if retrieved_path.exists() else []
        record = model.generate_json_record(
            _judge_prompt(question, row, answer, evidence),
            _judge_schema(),
            prompt_version="001_qa_judge",
        )
        call_path = model_call_root / f"{question.id}.json"
        _write_json(call_path, record.to_dict())
        if record.status == "ok":
            parsed = record.parsed_json
            row["llm_judge_status"] = "ok"
            row["llm_judge_supported"] = bool(parsed.get("supported"))
            row["llm_judge_score"] = float(parsed.get("score") or 0.0)
            row["llm_judge_notes"] = _clean(parsed.get("notes"))
            judged.append({"question_id": question.id, **parsed, "model_call_path": call_path.as_posix()})
        else:
            row["llm_judge_status"] = "error"
            row["llm_judge_supported"] = ""
            row["llm_judge_score"] = ""
            row["llm_judge_notes"] = record.error
            judged.append({"question_id": question.id, "error": record.error, "model_call_path": call_path.as_posix()})
            if config.fail_fast:
                raise RuntimeError(record.error or f"LLM judge failed for {question.id}")
    judged_ok = [item for item in judged if "error" not in item]
    return _write_json(
        report_path,
        {
            "created_at": _now_iso(),
            "enabled": True,
            "status": "complete",
            "provider": model.provider,
            "model": model.model,
            "question_count": len(question_rows),
            "judged_count": len(judged_ok),
            "supported_rate": _safe_ratio(sum(1 for item in judged_ok if item.get("supported")), len(judged_ok)),
            "mean_score": round(sum(float(item.get("score") or 0.0) for item in judged_ok) / len(judged_ok), 6)
            if judged_ok
            else 0.0,
            "judgments": judged,
        },
    )


def _aggregate_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    ok_rows = [row for row in rows if row.get("status") == "ok"]
    metrics = {
        "question_count": total,
        "success_count": len(ok_rows),
        "error_count": total - len(ok_rows),
        "retrieval_recall": _safe_ratio(sum(1 for row in rows if row["retrieval_success"]), total),
        "answer_accuracy": _safe_ratio(sum(1 for row in rows if row["answer_success"]), total),
        "abstention_accuracy": _safe_ratio(sum(1 for row in rows if row["abstention_correct"]), total),
        "citation_support_rate": _safe_ratio(sum(1 for row in rows if row["citation_supported"]), total),
        "unsupported_answer_rate": _safe_ratio(sum(1 for row in rows if row["unsupported_answer"]), total),
        "mean_fact_coverage": round(sum(float(row["fact_coverage"]) for row in rows) / total, 6) if total else 0.0,
        "mean_entity_coverage": round(sum(float(row["entity_coverage"]) for row in rows) / total, 6) if total else 0.0,
        "mean_relationship_coverage": round(sum(float(row["relationship_coverage"]) for row in rows) / total, 6) if total else 0.0,
        "path_complete_rate": _safe_ratio(sum(1 for row in rows if row["path_complete"]), total),
    }
    multi_hop_rows = [row for row in rows if int(row.get("hop_count") or 0) > 1]
    metrics["multi_hop_retrieval_recall"] = _safe_ratio(
        sum(1 for row in multi_hop_rows if row["retrieval_success"]),
        len(multi_hop_rows),
    )
    judged_rows = [row for row in rows if row.get("llm_judge_status") == "ok"]
    if judged_rows:
        metrics["llm_judge_supported_rate"] = _safe_ratio(
            sum(1 for row in judged_rows if row.get("llm_judge_supported") is True),
            len(judged_rows),
        )
        metrics["mean_llm_judge_score"] = round(
            sum(float(row.get("llm_judge_score") or 0.0) for row in judged_rows) / len(judged_rows),
            6,
        )
    return metrics


def _bucket_metrics(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    buckets = sorted({_clean(row.get(key)) or "unspecified" for row in rows})
    return {bucket: _aggregate_metrics([row for row in rows if (_clean(row.get(key)) or "unspecified") == bucket]) for bucket in buckets}


def _metrics_rows(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [{"scope": "overall", "label": "", **metrics["overall"]}]
    for scope in ("question_types", "splits"):
        for label, payload in metrics[scope].items():
            rows.append({"scope": scope[:-1], "label": label, **payload})
    return rows


def _write_summary(path: Path, result: dict[str, Any]) -> Path:
    overall = result["metrics"]["overall"]
    lines = [
        f"# QA Evaluation: {result['eval_id']}",
        "",
        f"- Question set: `{result['question_set_id']}`",
        f"- Model profile: `{result['model_profile']['name']}`",
        f"- Retriever: `{result['model_profile']['qa_retriever']}`",
        f"- Questions: {overall['success_count']}/{overall['question_count']} succeeded",
        f"- Graph run ID: `{result['graph_provenance']['graph_run_id']}`",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Retrieval recall | {overall['retrieval_recall']} |",
        f"| Answer accuracy | {overall['answer_accuracy']} |",
        f"| Mean fact coverage | {overall['mean_fact_coverage']} |",
        f"| Citation support rate | {overall['citation_support_rate']} |",
        f"| Unsupported answer rate | {overall['unsupported_answer_rate']} |",
        f"| Abstention accuracy | {overall['abstention_accuracy']} |",
        f"| Path complete rate | {overall['path_complete_rate']} |",
        f"| Multi-hop retrieval recall | {overall['multi_hop_retrieval_recall']} |",
        "",
        "## Artifacts",
        "",
    ]
    mlflow_payload = result.get("mlflow") if isinstance(result.get("mlflow"), dict) else {}
    if mlflow_payload.get("enabled"):
        lines[7:7] = [
            f"- MLflow experiment: `{mlflow_payload.get('experiment', '')}`",
            f"- MLflow run ID: `{mlflow_payload.get('run_id', '')}`",
            f"- MLflow status: `{mlflow_payload.get('status', '')}`",
        ]
    for key in (
        "eval_manifest_path",
        "metrics_path",
        "metrics_csv_path",
        "question_results_path",
        "errors_path",
        "gold_snapshot_path",
        "artifact_manifest_path",
    ):
        value = result.get(key)
        if value:
            lines.append(f"- `{key}`: `{value}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _start_mlflow_run(config: QAEvaluationConfig, eval_id: str) -> tuple[Any | None, dict[str, Any]]:
    if not config.mlflow:
        return None, {"enabled": False}
    try:
        import mlflow
    except ImportError as exc:
        raise RuntimeError("Install mlflow or run without QA mlflow.enabled to skip experiment logging.") from exc

    if config.mlflow_tracking_uri:
        mlflow.set_tracking_uri(config.mlflow_tracking_uri)
    if config.mlflow_experiment:
        mlflow.set_experiment(config.mlflow_experiment)
    run_name = config.mlflow_run_name or eval_id
    active_run = mlflow.start_run(run_name=run_name)
    info = getattr(active_run, "info", None)
    return mlflow, {
        "enabled": True,
        "status": "started",
        "tracking_uri": config.mlflow_tracking_uri,
        "experiment": config.mlflow_experiment,
        "run_name": run_name,
        "run_id": getattr(info, "run_id", ""),
        "artifact_uri": getattr(info, "artifact_uri", ""),
    }


def _log_mlflow_result(mlflow: Any, config: QAEvaluationConfig, result: dict[str, Any], eval_root: Path) -> dict[str, Any]:
    params = {
        "eval_id": result["eval_id"],
        "question_set_id": result["question_set_id"],
        "question_file": result["question_file"],
        "graph_run_id": result["graph_provenance"]["graph_run_id"],
        "graph_source": result["graph_provenance"]["graph_source"],
        "model_profile": result["model_profile"]["name"],
        "qa_provider": result["model_profile"]["qa_provider"],
        "qa_model": result["model_profile"]["qa_model"],
        "qa_retriever": result["model_profile"]["qa_retriever"],
        "max_evidence": config.max_evidence,
        "skip_answer": config.skip_answer,
        "llm_judge_enabled": config.llm_judge_enabled,
    }
    for key, value in params.items():
        mlflow.log_param(key, value)
    for metric_name, value in result["metrics"]["overall"].items():
        if isinstance(value, int | float):
            mlflow.log_metric(metric_name, value)
    if config.mlflow_log_artifacts:
        mlflow.log_artifacts(eval_root.as_posix())
    return {"status": "logged", "logged_artifacts": bool(config.mlflow_log_artifacts)}


def run_qa_evaluation(config: QAEvaluationConfig) -> dict[str, Any]:
    if config.max_evidence <= 0:
        raise ValueError("max_evidence must be positive")
    eval_id = config.eval_id or _eval_id()
    eval_root = config.output_root / eval_id
    if eval_root.exists() and not config.force:
        raise RuntimeError(f"QA evaluation output directory already exists: {eval_root}")
    if eval_root.exists():
        shutil.rmtree(eval_root)
    eval_root.mkdir(parents=True, exist_ok=True)
    (eval_root / "model_calls").mkdir(parents=True, exist_ok=True)

    mlflow_client, mlflow_result = _start_mlflow_run(config, eval_id)
    try:
        profile = resolve_model_profile(
            config.model_profile,
            qa_provider=config.answerer_provider,
            qa_model=config.model,
            qa_retriever=config.retriever,
        )
        questions_payload = _read_json(config.question_file)
        question_set_id = _clean(questions_payload.get("question_set_id")) or config.question_file.stem
        questions = read_question_file(config.question_file, config.limit)
        gold_snapshot_path = eval_root / "gold_snapshot" / config.question_file.name
        gold_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(config.question_file, gold_snapshot_path)

        pipeline_results = process_questions(
            QAConfig(
                questions=questions,
                output_root=eval_root,
                clean_output=False,
                model_profile=profile.name,
                answerer_provider=profile.qa_provider,
                model=profile.qa_model,
                retriever=profile.qa_retriever,
                graph_run_id=config.graph_run_id,
                max_evidence=config.max_evidence,
                skip_answer=config.skip_answer,
                fail_fast=config.fail_fast,
                limit=None,
            )
        )
        manifest_rows = {row["question_id"]: row for row in _read_csv_rows(eval_root / "manifest.csv")}
        question_rows = [_score_question(question, manifest_rows.get(question.id, {}), eval_root) for question in questions]
        llm_judge_path = _apply_llm_judge(config, questions, question_rows, manifest_rows, eval_root)
        metrics = {
            "overall": _aggregate_metrics(question_rows),
            "question_types": _bucket_metrics(question_rows, "question_type"),
            "splits": _bucket_metrics(question_rows, "split"),
        }
        metrics_path = _write_json(eval_root / "metrics.json", metrics)
        metrics_csv_path = _write_csv(
            eval_root / "metrics.csv",
            [
                "scope",
                "label",
                "question_count",
                "success_count",
                "error_count",
                "retrieval_recall",
                "answer_accuracy",
                "abstention_accuracy",
                "citation_support_rate",
                "unsupported_answer_rate",
                "mean_fact_coverage",
                "mean_entity_coverage",
                "mean_relationship_coverage",
                "path_complete_rate",
                "multi_hop_retrieval_recall",
                "llm_judge_supported_rate",
                "mean_llm_judge_score",
            ],
            _metrics_rows(metrics),
        )
        question_results_path = _write_csv(
            eval_root / "question_results.csv",
            [
                "question_id",
                "question",
                "question_type",
                "split",
                "status",
                "answer_status",
                "retrieved_count",
                "source_count",
                "hop_count",
                "max_retrieved_path_length",
                "path_complete",
                "definition_source_hit",
                "expected_fact_hits",
                "expected_fact_total",
                "fact_coverage",
                "entity_hits",
                "entity_total",
                "entity_coverage",
                "relationship_hits",
                "relationship_total",
                "relationship_coverage",
                "expected_evidence_hit",
                "retrieval_success",
                "citation_supported",
                "abstained",
                "expected_abstention",
                "abstention_correct",
                "unsupported_answer",
                "llm_judge_status",
                "llm_judge_supported",
                "llm_judge_score",
                "llm_judge_notes",
                "answer_success",
                "error",
            ],
            question_rows,
        )
        errors_path = _write_csv(
            eval_root / "errors.csv",
            ["question_id", "question", "stage", "error"],
            [
                {
                    "question_id": row["question_id"],
                    "question": row["question"],
                    "stage": "qa",
                    "error": row["error"],
                }
                for row in question_rows
                if row.get("error")
            ],
        )
        summary_path = eval_root / "summary.md"
        manifest_path = eval_root / "eval_manifest.json"
        artifact_manifest_path = eval_root / "artifact_manifest.json"
        result = {
            "eval_id": eval_id,
            "created_at": _now_iso(),
            "mode": "qa_evaluation",
            "question_file": config.question_file.as_posix(),
            "question_set_id": question_set_id,
            "output_root": eval_root.as_posix(),
            "graph_provenance": {
                "graph_run_id": config.graph_run_id,
                "graph_source": config.graph_source,
                "read_only": True,
            },
            "model_profile": profile.to_dict(),
            "config": asdict(config)
            | {
                "question_file": config.question_file.as_posix(),
                "output_root": config.output_root.as_posix(),
            },
            "question_count": len(questions),
            "success_count": sum(1 for item in pipeline_results if item.status == "ok"),
            "error_count": sum(1 for item in pipeline_results if item.status == "error"),
            "metrics": metrics,
            "mlflow": mlflow_result,
            "manifest_csv_path": (eval_root / "manifest.csv").as_posix(),
            "metrics_path": metrics_path.as_posix(),
            "metrics_csv_path": metrics_csv_path.as_posix(),
            "question_results_path": question_results_path.as_posix(),
            "errors_path": errors_path.as_posix(),
            "gold_snapshot_path": gold_snapshot_path.as_posix(),
            "llm_judge_report_path": llm_judge_path.as_posix(),
            "summary_path": summary_path.as_posix(),
            "eval_manifest_path": manifest_path.as_posix(),
            "artifact_manifest_path": artifact_manifest_path.as_posix(),
        }
        _write_summary(summary_path, result)
        _write_json(manifest_path, result)
        artifact_inputs = [
            manifest_path,
            summary_path,
            metrics_path,
            metrics_csv_path,
            question_results_path,
            errors_path,
            eval_root / "manifest.csv",
            gold_snapshot_path,
            llm_judge_path,
            *sorted((eval_root / "answers").glob("*.json")),
            *sorted((eval_root / "retrieved").glob("*.json")),
        ]
        _write_artifact_manifest(eval_root, artifact_inputs)
        if mlflow_client is not None:
            mlflow_update = _log_mlflow_result(mlflow_client, config, result, eval_root)
            result["mlflow"] = result["mlflow"] | mlflow_update
            _write_summary(summary_path, result)
            _write_json(manifest_path, result)
            _write_artifact_manifest(eval_root, artifact_inputs)
        return result
    finally:
        if mlflow_client is not None:
            mlflow_client.end_run()


__all__ = [
    "DEFAULT_QA_EVAL_OUTPUT_ROOT",
    "DEFAULT_QA_QUESTION_FILE",
    "QAEvaluationConfig",
    "run_qa_evaluation",
]
