from __future__ import annotations

import csv
import hashlib
import json
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from packages.llm.profiles import resolve_model_profile
from pipelines.annotation.review_workbook import ReviewWorkbook, read_review_workbook
from pipelines.ingestion.extractors import get_extractor
from pipelines.ingestion.models import ChunkRecord, ExtractionContext
from pipelines.ingestion.non_instruct import (
    DEFAULT_TERMINOLOGY_PATH,
    NonInstructPipelineConfig,
    RelationScoringConfig,
)
from pipelines.ingestion.validation import normalize_name, validate_extraction_output


DEFAULT_ANNOTATION_EVAL_OUTPUT_ROOT = Path("data/annotations/eval_v001")
DEFAULT_GOLD_MANIFEST_PATH = Path("data/annotations/gold_v001/bootstrap_v001_full/gold_manifest.json")
ARTIFACT_ONLY_NEO4J_LOAD_MODE = "none"
NEO4J_LOAD_MODES = {"none", "gold", "predictions", "both"}


@dataclass(frozen=True)
class AnnotationEvaluationConfig:
    gold_manifest_path: Path = DEFAULT_GOLD_MANIFEST_PATH
    output_root: Path = DEFAULT_ANNOTATION_EVAL_OUTPUT_ROOT
    eval_id: str | None = None
    model_profile: str = "noop"
    model: str | None = None
    entity_model: str | None = None
    embedding_model: str | None = None
    terminology_path: Path | None = DEFAULT_TERMINOLOGY_PATH
    entity_threshold: float = 0.5
    concept_threshold: float = 0.84
    relation_threshold: float = 0.66
    semantic_floor: float = 0.52
    semantic_weight: float = 0.50
    cue_weight: float = 0.25
    proximity_weight: float = 0.10
    entity_confidence_weight: float = 0.15
    max_pair_distance: int = 300
    min_confidence: float = 0.5
    limit: int | None = None
    force: bool = False
    fail_fast: bool = False
    neo4j_load_mode: str = ARTIFACT_ONLY_NEO4J_LOAD_MODE
    apply_schema: bool = False
    neo4j_run_label: str = ""
    mlflow: bool = False
    mlflow_tracking_uri: str = "http://localhost:5000"
    mlflow_experiment: str = "medgraphrag-annotation-eval"
    mlflow_run_name: str = ""
    mlflow_log_artifacts: bool = True


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _eval_id() -> str:
    return datetime.now(UTC).strftime("annotation-eval-%Y%m%d%H%M%S")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_metric_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"_", "-", ".", "/"} else "_" for char in value)


def _validate_artifact_only_config(config: AnnotationEvaluationConfig) -> None:
    bounded_values = {
        "min_confidence": config.min_confidence,
        "entity_threshold": config.entity_threshold,
        "concept_threshold": config.concept_threshold,
        "relation_threshold": config.relation_threshold,
        "semantic_floor": config.semantic_floor,
    }
    for name, value in bounded_values.items():
        if not 0 <= value <= 1:
            raise ValueError(f"{name} must be between 0 and 1")
    weights = {
        "semantic_weight": config.semantic_weight,
        "cue_weight": config.cue_weight,
        "proximity_weight": config.proximity_weight,
        "entity_confidence_weight": config.entity_confidence_weight,
    }
    if any(value < 0 for value in weights.values()) or sum(weights.values()) <= 0:
        raise ValueError("Non-instruct score weights must be non-negative and sum to more than zero")
    if config.max_pair_distance <= 0:
        raise ValueError("max_pair_distance must be positive")
    if config.neo4j_load_mode not in NEO4J_LOAD_MODES:
        supported = ", ".join(sorted(NEO4J_LOAD_MODES))
        raise ValueError(f"Unsupported Neo4j load mode: {config.neo4j_load_mode}. Supported modes: {supported}")
    if config.neo4j_load_mode != ARTIFACT_ONLY_NEO4J_LOAD_MODE:
        raise ValueError(
            "Annotation evaluation is artifact-only. "
            "Neo4j loading must be run as a separate explicit ingestion step."
        )
    if config.apply_schema:
        raise ValueError("Annotation evaluation is artifact-only and will not apply the Neo4j schema.")
    if config.neo4j_run_label:
        raise ValueError("Annotation evaluation is artifact-only; omit --neo4j-run-label until Neo4j loading is enabled.")


def _project_path(path: str | Path, base: Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else base / candidate


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _canon_type(value: Any) -> str:
    return _clean(value)


def _canon_name(value: Any) -> str:
    return normalize_name(_clean(value))


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _document_by_id(review: ReviewWorkbook) -> dict[str, dict[str, Any]]:
    return {_clean(row.get("document_id")): row for row in review.documents if _clean(row.get("document_id"))}


def _document_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _clean(row.get("document_id")),
        "pmid": _clean(row.get("pmid")),
        "pmcid": _clean(row.get("pmcid")),
        "title": _clean(row.get("title")),
        "year": _clean(row.get("year")),
        "journal": _clean(row.get("journal")),
        "doi": _clean(row.get("doi")),
        "authors": [item.strip() for item in _clean(row.get("authors")).split(";") if item.strip()],
        "abstract": _clean(row.get("abstract")),
        "source_url": _clean(row.get("source_url")),
        "source": "annotation_gold",
    }


def _chunk_record(row: dict[str, Any]) -> ChunkRecord:
    return ChunkRecord(
        id=_clean(row.get("chunk_id")),
        document_id=_clean(row.get("document_id")),
        pmcid=_clean(row.get("pmcid")),
        order=_safe_int(row.get("chunk_index")),
        char_start=_safe_int(row.get("start_char")),
        char_end=_safe_int(row.get("end_char")),
        section=_clean(row.get("chunk_section")),
        type=_clean(row.get("chunk_section")) or "unknown",
        source_sections=[_clean(row.get("chunk_section"))] if _clean(row.get("chunk_section")) else [],
        text=_clean(row.get("chunk_text")),
    )


def _selected_chunks(review: ReviewWorkbook, limit: int | None) -> list[ChunkRecord]:
    chunks = [
        _chunk_record(row)
        for row in review.chunks
        if _clean(row.get("chunk_id")) and _clean(row.get("included_in_gold_annotation")).casefold() != "no"
    ]
    chunks.sort(key=lambda item: (item.pmcid, item.order, item.id))
    return chunks[:limit] if limit is not None else chunks


def _gold_entity_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _clean(row.get("chunk_id")),
        _canon_type(row.get("entity_type")),
        _canon_name(row.get("normalized_name") or row.get("entity_text")),
    )


def _prediction_entity_key(chunk_id: str, entity: dict[str, Any]) -> tuple[str, str, str]:
    return (chunk_id, _canon_type(entity.get("type")), _canon_name(entity.get("name")))


def _gold_relationship_key(row: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
    return (
        _clean(row.get("chunk_id")),
        _clean(row.get("relationship_type")).upper(),
        _canon_type(row.get("source_entity_type")),
        _canon_name(row.get("source_normalized_name") or row.get("source_entity_text")),
        _canon_type(row.get("target_entity_type")),
        _canon_name(row.get("target_normalized_name") or row.get("target_entity_text")),
    )


def _prediction_relationship_key(chunk_id: str, relationship: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
    source = relationship.get("source") if isinstance(relationship.get("source"), dict) else {}
    target = relationship.get("target") if isinstance(relationship.get("target"), dict) else {}
    return (
        chunk_id,
        _clean(relationship.get("type")).upper(),
        _canon_type(source.get("type")),
        _canon_name(source.get("name")),
        _canon_type(target.get("type")),
        _canon_name(target.get("name")),
    )


def _metrics(tp: int, fp: int, fn: int) -> dict[str, Any]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    return {
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
    }


def _metrics_by_bucket(
    gold_keys: set[tuple[Any, ...]],
    prediction_keys: set[tuple[Any, ...]],
    bucket_index: int,
) -> dict[str, dict[str, Any]]:
    buckets = sorted({str(key[bucket_index]) for key in gold_keys | prediction_keys})
    metrics: dict[str, dict[str, Any]] = {}
    for bucket in buckets:
        gold_bucket = {key for key in gold_keys if str(key[bucket_index]) == bucket}
        prediction_bucket = {key for key in prediction_keys if str(key[bucket_index]) == bucket}
        tp = len(gold_bucket & prediction_bucket)
        metrics[bucket] = _metrics(
            tp,
            len(prediction_bucket - gold_bucket),
            len(gold_bucket - prediction_bucket),
        )
    return metrics


def _key_text(key: tuple[Any, ...]) -> str:
    return "|".join(str(item) for item in key)


def _entity_match_rows(
    gold_keys: set[tuple[Any, ...]],
    prediction_keys: set[tuple[Any, ...]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for outcome, keys in (
        ("tp", gold_keys & prediction_keys),
        ("fp", prediction_keys - gold_keys),
        ("fn", gold_keys - prediction_keys),
    ):
        for chunk_id, entity_type, entity_name in sorted(keys):
            rows.append(
                {
                    "outcome": outcome,
                    "chunk_id": str(chunk_id),
                    "entity_type": str(entity_type),
                    "entity_name": str(entity_name),
                    "entity_key": _key_text((chunk_id, entity_type, entity_name)),
                }
            )
    return rows


def _relationship_match_rows(
    gold_keys: set[tuple[Any, ...]],
    prediction_keys: set[tuple[Any, ...]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for outcome, keys in (
        ("tp", gold_keys & prediction_keys),
        ("fp", prediction_keys - gold_keys),
        ("fn", gold_keys - prediction_keys),
    ):
        for chunk_id, relationship_type, source_type, source_name, target_type, target_name in sorted(keys):
            rows.append(
                {
                    "outcome": outcome,
                    "chunk_id": str(chunk_id),
                    "relationship_type": str(relationship_type),
                    "source_entity_type": str(source_type),
                    "source_entity_name": str(source_name),
                    "target_entity_type": str(target_type),
                    "target_entity_name": str(target_name),
                    "relationship_key": _key_text(
                        (chunk_id, relationship_type, source_type, source_name, target_type, target_name)
                    ),
                }
            )
    return rows


def _score_predictions(
    gold_entities: list[dict[str, Any]],
    gold_relationships: list[dict[str, Any]],
    processed_records: list[dict[str, Any]],
    evaluated_chunk_ids: set[str],
) -> tuple[dict[str, Any], list[dict[str, str]], list[dict[str, str]]]:
    gold_entity_keys = {_gold_entity_key(row) for row in gold_entities if _clean(row.get("chunk_id")) in evaluated_chunk_ids}
    gold_relationship_keys = {
        _gold_relationship_key(row) for row in gold_relationships if _clean(row.get("chunk_id")) in evaluated_chunk_ids
    }
    prediction_entity_keys: set[tuple[str, str, str]] = set()
    prediction_relationship_keys: set[tuple[str, str, str, str, str, str]] = set()

    for record in processed_records:
        for extraction in record.get("extractions") or []:
            if not isinstance(extraction, dict) or extraction.get("status") != "ok":
                continue
            chunk_id = _clean(extraction.get("chunk_id"))
            for entity in extraction.get("entities") or []:
                if isinstance(entity, dict):
                    prediction_entity_keys.add(_prediction_entity_key(chunk_id, entity))
            for relationship in extraction.get("relationships") or []:
                if isinstance(relationship, dict):
                    prediction_relationship_keys.add(_prediction_relationship_key(chunk_id, relationship))

    entity_tp = len(gold_entity_keys & prediction_entity_keys)
    relationship_tp = len(gold_relationship_keys & prediction_relationship_keys)
    metrics = {
        "entities": _metrics(
            entity_tp,
            len(prediction_entity_keys - gold_entity_keys),
            len(gold_entity_keys - prediction_entity_keys),
        ),
        "relationships": _metrics(
            relationship_tp,
            len(prediction_relationship_keys - gold_relationship_keys),
            len(gold_relationship_keys - prediction_relationship_keys),
        ),
    }
    metrics["overall"] = _metrics(
        metrics["entities"]["true_positive"] + metrics["relationships"]["true_positive"],
        metrics["entities"]["false_positive"] + metrics["relationships"]["false_positive"],
        metrics["entities"]["false_negative"] + metrics["relationships"]["false_negative"],
    )
    metrics["entity_types"] = _metrics_by_bucket(gold_entity_keys, prediction_entity_keys, 1)
    metrics["relationship_types"] = _metrics_by_bucket(gold_relationship_keys, prediction_relationship_keys, 1)
    return (
        metrics,
        _entity_match_rows(gold_entity_keys, prediction_entity_keys),
        _relationship_match_rows(gold_relationship_keys, prediction_relationship_keys),
    )


def _metrics_rows(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for scope in ("overall", "entities", "relationships"):
        rows.append({"scope": scope, "label": "", **metrics[scope]})
    for entity_type, payload in metrics["entity_types"].items():
        rows.append({"scope": "entity_type", "label": entity_type, **payload})
    for relationship_type, payload in metrics["relationship_types"].items():
        rows.append({"scope": "relationship_type", "label": relationship_type, **payload})
    return rows


def _append_processed(
    records_by_document: dict[str, dict[str, Any]],
    document: dict[str, Any],
    chunk: ChunkRecord,
    extraction: dict[str, Any],
) -> None:
    record = records_by_document.setdefault(
        document["id"],
        {
            "document": document,
            "chunks": [],
            "extractions": [],
            "entities": [],
            "relationships": [],
            "rejected_candidates": [],
        },
    )
    record["chunks"].append(chunk.to_dict())
    record["extractions"].append(extraction)
    if extraction.get("status") == "ok":
        record["entities"].extend(extraction.get("entities") or [])
        record["relationships"].extend(extraction.get("relationships") or [])
        record["rejected_candidates"].extend(extraction.get("rejected_candidates") or [])


def _dedupe_by_id(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    fallback: list[dict[str, Any]] = []
    for item in items:
        item_id = _clean(item.get("id")) if isinstance(item, dict) else ""
        if item_id:
            deduped[item_id] = item
        elif isinstance(item, dict):
            fallback.append(item)
    return list(deduped.values()) + fallback


def _finalize_processed_records(
    records_by_document: dict[str, dict[str, Any]],
    *,
    run_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for record in sorted(records_by_document.values(), key=lambda item: _clean(item["document"].get("pmcid"))):
        record["run"] = run_payload
        record["chunks"].sort(key=lambda item: (_safe_int(item.get("order")), _clean(item.get("id"))))
        record["entities"] = _dedupe_by_id(record["entities"])
        record["relationships"] = _dedupe_by_id(record["relationships"])
        records.append(record)
    return records


def _write_processed_records(processed_records: list[dict[str, Any]], processed_root: Path) -> list[str]:
    paths: list[str] = []
    for record in processed_records:
        pmcid = _clean(record["document"].get("pmcid")) or _clean(record["document"].get("id")).replace(":", "_")
        path = _write_json(processed_root / f"{pmcid}.json", record)
        paths.append(path.as_posix())
    return paths


def _load_gold_inputs(gold_manifest_path: Path) -> tuple[dict[str, Any], ReviewWorkbook, list[dict[str, str]], list[dict[str, str]]]:
    manifest = _read_json(gold_manifest_path)
    project_root = Path.cwd()
    artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), dict) else {}
    workbook_artifact = artifacts.get("reviewed_workbook") if isinstance(artifacts.get("reviewed_workbook"), dict) else {}
    entities_artifact = artifacts.get("gold_entities") if isinstance(artifacts.get("gold_entities"), dict) else {}
    relationships_artifact = artifacts.get("gold_relationships") if isinstance(artifacts.get("gold_relationships"), dict) else {}
    workbook_path = _project_path(workbook_artifact.get("path") or "", project_root)
    entities_path = _project_path(entities_artifact.get("path") or "", project_root)
    relationships_path = _project_path(relationships_artifact.get("path") or "", project_root)
    return manifest, read_review_workbook(workbook_path), _read_csv(entities_path), _read_csv(relationships_path)


def _snapshot_gold_artifacts(gold_manifest_path: Path, manifest: dict[str, Any], snapshot_root: Path) -> dict[str, Any]:
    snapshot_root.mkdir(parents=True, exist_ok=True)
    project_root = Path.cwd()
    copied: dict[str, Any] = {}
    manifest_destination = snapshot_root / "gold_manifest.json"
    shutil.copy2(gold_manifest_path, manifest_destination)
    copied["gold_manifest"] = {
        "source_path": gold_manifest_path.as_posix(),
        "snapshot_path": manifest_destination.as_posix(),
        "sha256": _sha256_file(manifest_destination),
    }

    artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), dict) else {}
    for name in ("reviewed_workbook", "gold_entities", "gold_relationships"):
        payload = artifacts.get(name) if isinstance(artifacts.get(name), dict) else {}
        source_value = payload.get("path")
        if not source_value:
            continue
        source = _project_path(source_value, project_root)
        destination = snapshot_root / source.name
        shutil.copy2(source, destination)
        copied[name] = {
            "source_path": source.as_posix(),
            "snapshot_path": destination.as_posix(),
            "sha256": _sha256_file(destination),
        }

    snapshot_manifest_path = _write_json(
        snapshot_root / "snapshot_manifest.json",
        {
            "created_at": _now_iso(),
            "gold_set_id": manifest.get("gold_set_id", ""),
            "artifacts": copied,
        },
    )
    return {
        "snapshot_root": snapshot_root.as_posix(),
        "snapshot_manifest_path": snapshot_manifest_path.as_posix(),
        "artifacts": copied,
    }


def _error_rows(chunk_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": item.get("chunk_id", ""),
            "document_id": item.get("document_id", ""),
            "pmcid": item.get("pmcid", ""),
            "stage": "extraction",
            "error": item.get("error", ""),
        }
        for item in chunk_results
        if item.get("status") == "error"
    ]


def _write_summary(path: Path, result: dict[str, Any]) -> Path:
    metrics = result["metrics"]
    lines = [
        f"# Annotation Evaluation: {result['eval_id']}",
        "",
        f"- Gold set: `{result['gold_set_id']}`",
        f"- Model profile: `{result['model_profile']['name']}`",
        f"- Artifact-only: `{str(result['artifact_policy']['artifact_only']).lower()}`",
        f"- Chunks: {result['success_count']}/{result['chunk_count']} succeeded",
        f"- Errors: {result['error_count']}",
        "",
        "## Metrics",
        "",
        "| Scope | Precision | Recall | F1 | TP | FP | FN |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    mlflow_payload = result.get("mlflow") if isinstance(result.get("mlflow"), dict) else {}
    if mlflow_payload.get("enabled"):
        lines[7:7] = [
            f"- MLflow experiment: `{mlflow_payload.get('experiment', '')}`",
            f"- MLflow run ID: `{mlflow_payload.get('run_id', '')}`",
            f"- MLflow status: `{mlflow_payload.get('status', '')}`",
        ]
    for scope in ("overall", "entities", "relationships"):
        payload = metrics[scope]
        lines.append(
            f"| {scope} | {payload['precision']} | {payload['recall']} | {payload['f1']} | "
            f"{payload['true_positive']} | {payload['false_positive']} | {payload['false_negative']} |"
        )
    lines.extend(["", "## Artifacts", ""])
    for key in (
        "eval_manifest_path",
        "metrics_path",
        "metrics_csv_path",
        "entity_matches_path",
        "relationship_matches_path",
        "chunk_results_path",
        "errors_path",
        "gold_snapshot_manifest_path",
        "neo4j_load_report_path",
        "artifact_manifest_path",
    ):
        value = result.get(key)
        if value:
            lines.append(f"- `{key}`: `{value}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _artifact_record(path: Path) -> dict[str, Any]:
    return {"path": path.as_posix(), "sha256": _sha256_file(path)}


def _write_artifact_manifest(eval_root: Path, artifact_paths: list[Path]) -> Path:
    records = [_artifact_record(path) for path in artifact_paths if path.exists()]
    return _write_json(
        eval_root / "artifact_manifest.json",
        {
            "created_at": _now_iso(),
            "artifact_count": len(records),
            "artifacts": records,
        },
    )


def _start_mlflow_run(config: AnnotationEvaluationConfig, eval_id: str) -> tuple[Any | None, dict[str, Any]]:
    if not config.mlflow:
        return None, {"enabled": False}
    try:
        import mlflow
    except ImportError as exc:
        raise RuntimeError("Install mlflow or run without --mlflow to skip experiment logging.") from exc

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


def _log_mlflow_result(
    mlflow: Any,
    config: AnnotationEvaluationConfig,
    result: dict[str, Any],
    eval_root: Path,
) -> dict[str, Any]:
    params = {
        "eval_id": result["eval_id"],
        "gold_set_id": result["gold_set_id"],
        "gold_manifest_path": result["gold_manifest_path"],
        "model_profile": result["model_profile"]["name"],
        "extractor_provider": result["model_profile"]["extractor_provider"],
        "extractor_model": result["model_profile"]["extractor_model"],
        "entity_model": result["model_profile"].get("entity_model", ""),
        "min_confidence": config.min_confidence,
        "entity_threshold": config.entity_threshold,
        "embedding_model": config.embedding_model or result["model_profile"]["extractor_model"],
        "terminology_path": config.terminology_path.as_posix() if config.terminology_path else "",
        "concept_threshold": config.concept_threshold,
        "relation_threshold": config.relation_threshold,
        "semantic_floor": config.semantic_floor,
        "semantic_weight": config.semantic_weight,
        "cue_weight": config.cue_weight,
        "proximity_weight": config.proximity_weight,
        "entity_confidence_weight": config.entity_confidence_weight,
        "max_pair_distance": config.max_pair_distance,
        "chunk_count": result["chunk_count"],
        "success_count": result["success_count"],
        "error_count": result["error_count"],
        "artifact_only": result["artifact_policy"]["artifact_only"],
        "neo4j_load_mode": result["artifact_policy"]["neo4j_load_mode"],
    }
    for key, value in params.items():
        mlflow.log_param(key, value)

    for scope in ("overall", "entities", "relationships"):
        payload = result["metrics"][scope]
        for metric_name in ("precision", "recall", "f1", "true_positive", "false_positive", "false_negative"):
            mlflow.log_metric(f"{scope}_{metric_name}", payload[metric_name])

    for entity_type, payload in result["metrics"]["entity_types"].items():
        label = _safe_metric_name(entity_type)
        for metric_name in ("precision", "recall", "f1"):
            mlflow.log_metric(f"entity_type_{label}_{metric_name}", payload[metric_name])

    for relationship_type, payload in result["metrics"]["relationship_types"].items():
        label = _safe_metric_name(relationship_type)
        for metric_name in ("precision", "recall", "f1"):
            mlflow.log_metric(f"relationship_type_{label}_{metric_name}", payload[metric_name])

    if config.mlflow_log_artifacts:
        mlflow.log_artifacts(eval_root.as_posix())

    return {"status": "logged", "logged_artifacts": bool(config.mlflow_log_artifacts)}


def run_annotation_evaluation(config: AnnotationEvaluationConfig) -> dict[str, Any]:
    _validate_artifact_only_config(config)
    eval_id = config.eval_id or _eval_id()
    eval_root = config.output_root / eval_id
    if eval_root.exists() and not config.force:
        raise RuntimeError(f"Annotation evaluation output directory already exists: {eval_root}")
    eval_root.mkdir(parents=True, exist_ok=True)
    mlflow_client, mlflow_result = _start_mlflow_run(config, eval_id)

    try:
        profile = resolve_model_profile(
            config.model_profile,
            extractor_model=config.model,
            entity_model=config.entity_model,
        )
        non_instruct_config = NonInstructPipelineConfig(
            embedding_model=config.embedding_model or profile.extractor_model,
            terminology_path=config.terminology_path,
            entity_threshold=config.entity_threshold,
            concept_threshold=config.concept_threshold,
            relation_scoring=RelationScoringConfig(
                relation_threshold=config.relation_threshold,
                semantic_floor=config.semantic_floor,
                semantic_weight=config.semantic_weight,
                cue_weight=config.cue_weight,
                proximity_weight=config.proximity_weight,
                entity_confidence_weight=config.entity_confidence_weight,
                max_pair_distance=config.max_pair_distance,
            ),
        )
        model_call_root = eval_root / "model_calls"
        model_call_root.mkdir(parents=True, exist_ok=True)
        extractor = get_extractor(
            profile.extractor_provider,
            profile.extractor_model,
            profile.entity_model,
            model_call_root,
            entity_threshold=(
                config.entity_threshold
                if profile.extractor_provider in {
                    "gliner_ollama", "gliner-ollama", "gliner", "gliner_ner", "gliner-ner",
                    "non_instruct", "non-instruct", "gliner_semantic", "gliner-semantic",
                }
                else None
            ),
            non_instruct_config=(
                non_instruct_config
                if profile.extractor_provider in {"non_instruct", "non-instruct", "gliner_semantic", "gliner-semantic"}
                else None
            ),
        )
        manifest, review, gold_entities, gold_relationships = _load_gold_inputs(config.gold_manifest_path)
        gold_snapshot = _snapshot_gold_artifacts(config.gold_manifest_path, manifest, eval_root / "gold_snapshot")
        documents = _document_by_id(review)
        chunks = _selected_chunks(review, config.limit)
        records_by_document: dict[str, dict[str, Any]] = {}
        chunk_results: list[dict[str, Any]] = []
        started_at = _now_iso()

        for chunk in chunks:
            document_row = documents.get(chunk.document_id)
            if document_row is None:
                error = f"Chunk references unknown document_id: {chunk.document_id}"
                if config.fail_fast:
                    raise RuntimeError(error)
                chunk_results.append({"chunk_id": chunk.id, "status": "error", "error": error})
                continue
            document = _document_payload(document_row)
            context = ExtractionContext(
                extractor=extractor.provider,
                model=extractor.model,
                min_confidence=config.min_confidence,
                created_at=_now_iso(),
            )
            extraction: dict[str, Any] = {
                "chunk_id": chunk.id,
                "status": "pending",
                "entities": [],
                "relationships": [],
                "rejected_candidates": [],
            }
            try:
                raw_output = extractor.extract(document, chunk)
                model_call_paths = list(getattr(extractor, "last_model_call_paths", []))
                normalized = validate_extraction_output(raw_output, document, chunk, context)
                extraction.update(
                    {
                        "status": "ok",
                        "entities": normalized["entities"],
                        "relationships": normalized["relationships"],
                        "rejected_candidates": normalized["rejected_candidates"],
                    }
                )
                if model_call_paths:
                    extraction["model_call_paths"] = model_call_paths
                chunk_results.append(
                    {
                        "chunk_id": chunk.id,
                        "document_id": chunk.document_id,
                        "pmcid": chunk.pmcid,
                        "status": "ok",
                        "entity_count": len(normalized["entities"]),
                        "relationship_count": len(normalized["relationships"]),
                        "rejected_candidate_count": len(normalized["rejected_candidates"]),
                        "model_call_count": len(model_call_paths),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                extraction.update({"status": "error", "error": str(exc)})
                chunk_results.append(
                    {
                        "chunk_id": chunk.id,
                        "document_id": chunk.document_id,
                        "pmcid": chunk.pmcid,
                        "status": "error",
                        "error": str(exc),
                    }
                )
                if config.fail_fast:
                    raise
            _append_processed(records_by_document, document, chunk, extraction)

        run_payload = {
            "id": eval_id,
            "created_at": started_at,
            "source": "annotation_gold_eval",
            "gold_set_id": manifest.get("gold_set_id", ""),
            "model_profile": profile.name,
            "extractor_provider": profile.extractor_provider,
            "extractor_model": extractor.model,
            "entity_model": profile.entity_model,
            "min_confidence": config.min_confidence,
            "entity_threshold": config.entity_threshold,
            "artifact_only": True,
            "neo4j_load_mode": ARTIFACT_ONLY_NEO4J_LOAD_MODE,
        }
        processed_records = _finalize_processed_records(records_by_document, run_payload=run_payload)
        processed_paths = _write_processed_records(processed_records, eval_root / "predictions" / "processed")
        evaluated_chunk_ids = {chunk.id for chunk in chunks}
        metrics, entity_match_rows, relationship_match_rows = _score_predictions(
            gold_entities,
            gold_relationships,
            processed_records,
            evaluated_chunk_ids,
        )
        metrics_path = _write_json(eval_root / "metrics.json", metrics)
        metrics_csv_path = _write_csv(
            eval_root / "metrics.csv",
            ["scope", "label", "true_positive", "false_positive", "false_negative", "precision", "recall", "f1"],
            _metrics_rows(metrics),
        )
        entity_matches_path = _write_csv(
            eval_root / "matches" / "entity_matches.csv",
            ["outcome", "chunk_id", "entity_type", "entity_name", "entity_key"],
            entity_match_rows,
        )
        relationship_matches_path = _write_csv(
            eval_root / "matches" / "relationship_matches.csv",
            [
                "outcome",
                "chunk_id",
                "relationship_type",
                "source_entity_type",
                "source_entity_name",
                "target_entity_type",
                "target_entity_name",
                "relationship_key",
            ],
            relationship_match_rows,
        )
        chunk_results_path = _write_csv(
            eval_root / "chunk_results.csv",
            [
                "chunk_id",
                "document_id",
                "pmcid",
                "status",
                "entity_count",
                "relationship_count",
                "rejected_candidate_count",
                "model_call_count",
                "error",
            ],
            chunk_results,
        )
        errors_path = _write_csv(
            eval_root / "errors.csv",
            ["chunk_id", "document_id", "pmcid", "stage", "error"],
            _error_rows(chunk_results),
        )
        neo4j_load_report_path = _write_json(
            eval_root / "neo4j_load_report.json",
            {
                "created_at": _now_iso(),
                "enabled": False,
                "neo4j_load_mode": ARTIFACT_ONLY_NEO4J_LOAD_MODE,
                "apply_schema": False,
                "loaded_entities": 0,
                "loaded_relationships": 0,
                "message": "Annotation evaluation is artifact-only; no Neo4j writes were attempted.",
            },
        )
        summary_path = eval_root / "summary.md"
        manifest_path = eval_root / "eval_manifest.json"
        artifact_manifest_path = eval_root / "artifact_manifest.json"
        result = {
            "eval_id": eval_id,
            "created_at": _now_iso(),
            "mode": "annotation_evaluation",
            "artifact_policy": {
                "artifact_only": True,
                "neo4j_load_mode": ARTIFACT_ONLY_NEO4J_LOAD_MODE,
                "apply_schema": False,
                "neo4j_run_label": "",
                "neo4j_ingestion": "disabled",
            },
            "mlflow": mlflow_result,
            "gold_manifest_path": config.gold_manifest_path.as_posix(),
            "gold_set_id": manifest.get("gold_set_id", ""),
            "output_root": eval_root.as_posix(),
            "model_profile": profile.to_dict(),
            "config": asdict(config)
            | {
                "gold_manifest_path": config.gold_manifest_path.as_posix(),
                "output_root": config.output_root.as_posix(),
                "terminology_path": config.terminology_path.as_posix() if config.terminology_path else None,
            },
            "chunk_count": len(chunks),
            "success_count": sum(1 for item in chunk_results if item.get("status") == "ok"),
            "error_count": sum(1 for item in chunk_results if item.get("status") == "error"),
            "processed_record_paths": processed_paths,
            "metrics_path": metrics_path.as_posix(),
            "metrics_csv_path": metrics_csv_path.as_posix(),
            "entity_matches_path": entity_matches_path.as_posix(),
            "relationship_matches_path": relationship_matches_path.as_posix(),
            "chunk_results_path": chunk_results_path.as_posix(),
            "errors_path": errors_path.as_posix(),
            "gold_snapshot_root": gold_snapshot["snapshot_root"],
            "gold_snapshot_manifest_path": gold_snapshot["snapshot_manifest_path"],
            "neo4j_load_report_path": neo4j_load_report_path.as_posix(),
            "summary_path": summary_path.as_posix(),
            "eval_manifest_path": manifest_path.as_posix(),
            "artifact_manifest_path": artifact_manifest_path.as_posix(),
            "metrics": metrics,
        }
        _write_summary(summary_path, result)
        _write_json(manifest_path, result)
        _write_artifact_manifest(
            eval_root,
            [
                manifest_path,
                summary_path,
                metrics_path,
                metrics_csv_path,
                entity_matches_path,
                relationship_matches_path,
                chunk_results_path,
                errors_path,
                neo4j_load_report_path,
                Path(gold_snapshot["snapshot_manifest_path"]),
                *[Path(item["snapshot_path"]) for item in gold_snapshot["artifacts"].values()],
                *[Path(path) for path in processed_paths],
                *(sorted(model_call_root.rglob("*.json")) if model_call_root.exists() else []),
            ],
        )
        if mlflow_client is not None:
            mlflow_update = _log_mlflow_result(mlflow_client, config, result, eval_root)
            result["mlflow"] = result["mlflow"] | mlflow_update
            _write_summary(summary_path, result)
            _write_json(manifest_path, result)
            _write_artifact_manifest(
                eval_root,
                [
                    manifest_path,
                    summary_path,
                    metrics_path,
                    metrics_csv_path,
                    entity_matches_path,
                    relationship_matches_path,
                    chunk_results_path,
                    errors_path,
                    neo4j_load_report_path,
                    Path(gold_snapshot["snapshot_manifest_path"]),
                    *[Path(item["snapshot_path"]) for item in gold_snapshot["artifacts"].values()],
                    *[Path(path) for path in processed_paths],
                    *(sorted(model_call_root.rglob("*.json")) if model_call_root.exists() else []),
                ],
            )
        return result
    finally:
        if mlflow_client is not None:
            mlflow_client.end_run()


__all__ = [
    "AnnotationEvaluationConfig",
    "ARTIFACT_ONLY_NEO4J_LOAD_MODE",
    "DEFAULT_ANNOTATION_EVAL_OUTPUT_ROOT",
    "DEFAULT_GOLD_MANIFEST_PATH",
    "NEO4J_LOAD_MODES",
    "run_annotation_evaluation",
]
