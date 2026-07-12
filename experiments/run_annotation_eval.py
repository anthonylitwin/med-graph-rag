from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipelines.annotation.evaluation import AnnotationEvaluationConfig, run_annotation_evaluation


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _project_path(value: Any, field: str) -> Path:
    text = _optional_text(value)
    if text is None:
        raise ValueError(f"annotation_eval.{field} is required")
    path = Path(text)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_annotation_eval_config(params_path: Path) -> AnnotationEvaluationConfig:
    payload = yaml.safe_load(params_path.read_text(encoding="utf-8")) or {}
    settings = payload.get("annotation_eval")
    if not isinstance(settings, dict):
        raise ValueError("params file must contain an annotation_eval mapping")

    mlflow = settings.get("mlflow") or {}
    if not isinstance(mlflow, dict):
        raise ValueError("annotation_eval.mlflow must be a mapping")
    non_instruct = settings.get("non_instruct") or {}
    if not isinstance(non_instruct, dict):
        raise ValueError("annotation_eval.non_instruct must be a mapping")

    eval_id = _optional_text(settings.get("eval_id"))
    if eval_id is None:
        raise ValueError("annotation_eval.eval_id is required for a stable DVC output")

    limit = settings.get("limit")
    return AnnotationEvaluationConfig(
        gold_manifest_path=_project_path(settings.get("gold_manifest"), "gold_manifest"),
        output_root=_project_path(settings.get("output_root"), "output_root"),
        eval_id=eval_id,
        model_profile=str(settings.get("model_profile", "noop")),
        model=_optional_text(settings.get("model")),
        entity_model=_optional_text(settings.get("entity_model")),
        embedding_model=_optional_text(non_instruct.get("embedding_model")),
        terminology_path=_project_path(
            non_instruct.get("terminology_path", "data/terminology/biomedical_aliases_v001.json"),
            "non_instruct.terminology_path",
        ),
        entity_threshold=float(non_instruct.get("entity_threshold", 0.5)),
        concept_threshold=float(non_instruct.get("concept_threshold", 0.84)),
        relation_threshold=float(non_instruct.get("relation_threshold", 0.66)),
        semantic_floor=float(non_instruct.get("semantic_floor", 0.52)),
        semantic_weight=float(non_instruct.get("semantic_weight", 0.50)),
        cue_weight=float(non_instruct.get("cue_weight", 0.25)),
        proximity_weight=float(non_instruct.get("proximity_weight", 0.10)),
        entity_confidence_weight=float(non_instruct.get("entity_confidence_weight", 0.15)),
        max_pair_distance=int(non_instruct.get("max_pair_distance", 300)),
        min_confidence=float(settings.get("min_confidence", 0.5)),
        limit=None if limit is None else int(limit),
        force=True,
        fail_fast=bool(settings.get("fail_fast", False)),
        neo4j_load_mode=str(settings.get("neo4j_load_mode", "none")),
        mlflow=bool(mlflow.get("enabled", False)),
        mlflow_tracking_uri=str(mlflow.get("tracking_uri", "http://localhost:5000")),
        mlflow_experiment=str(mlflow.get("experiment", "medgraphrag-annotation-eval")),
        mlflow_run_name=str(mlflow.get("run_name", "")),
        mlflow_log_artifacts=bool(mlflow.get("log_artifacts", True)),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the DVC-configured annotation evaluation")
    parser.add_argument("--params", type=Path, default=Path(__file__).with_name("params.yaml"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    params_path = args.params.resolve()
    os.chdir(PROJECT_ROOT)
    result = run_annotation_evaluation(load_annotation_eval_config(params_path))
    print(
        json.dumps(
            {
                "eval_id": result["eval_id"],
                "gold_set_id": result["gold_set_id"],
                "chunk_count": result["chunk_count"],
                "success_count": result["success_count"],
                "error_count": result["error_count"],
                "metrics": result["metrics"],
                "eval_manifest_path": result["eval_manifest_path"],
                "mlflow": result["mlflow"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
