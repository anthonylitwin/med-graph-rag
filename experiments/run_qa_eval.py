from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipelines.qa.evaluation import QAEvaluationConfig, run_qa_evaluation


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _project_path(value: Any, field: str) -> Path:
    text = _optional_text(value)
    if text is None:
        raise ValueError(f"qa_eval.{field} is required")
    path = Path(text)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_qa_eval_config(params_path: Path) -> QAEvaluationConfig:
    payload = yaml.safe_load(params_path.read_text(encoding="utf-8")) or {}
    settings = payload.get("qa_eval")
    if not isinstance(settings, dict):
        raise ValueError("params file must contain a qa_eval mapping")
    mlflow = settings.get("mlflow") or {}
    if not isinstance(mlflow, dict):
        raise ValueError("qa_eval.mlflow must be a mapping")

    eval_id = _optional_text(settings.get("eval_id"))
    if eval_id is None:
        raise ValueError("qa_eval.eval_id is required for a stable DVC output")

    limit = settings.get("limit")
    return QAEvaluationConfig(
        question_file=_project_path(settings.get("question_file"), "question_file"),
        output_root=_project_path(settings.get("output_root"), "output_root"),
        eval_id=eval_id,
        graph_run_id=str(settings.get("graph_run_id") or ""),
        graph_source=str(settings.get("graph_source") or ""),
        model_profile=str(settings.get("model_profile", "noop")),
        answerer_provider=_optional_text(settings.get("answerer_provider")),
        model=_optional_text(settings.get("model")),
        retriever=_optional_text(settings.get("retriever")),
        max_evidence=int(settings.get("max_evidence", 12)),
        skip_answer=bool(settings.get("skip_answer", False)),
        limit=None if limit is None else int(limit),
        force=True,
        fail_fast=bool(settings.get("fail_fast", False)),
        llm_judge_enabled=bool(settings.get("llm_judge", {}).get("enabled", False))
        if isinstance(settings.get("llm_judge"), dict)
        else False,
        llm_judge_provider=str(settings.get("llm_judge", {}).get("provider", "openai"))
        if isinstance(settings.get("llm_judge"), dict)
        else "openai",
        llm_judge_model=_optional_text(settings.get("llm_judge", {}).get("model"))
        if isinstance(settings.get("llm_judge"), dict)
        else None,
        mlflow=bool(mlflow.get("enabled", False)),
        mlflow_tracking_uri=str(mlflow.get("tracking_uri", "http://127.0.0.1:5000")),
        mlflow_experiment=str(mlflow.get("experiment", "medgraphrag-qa-eval")),
        mlflow_run_name=str(mlflow.get("run_name", "")),
        mlflow_log_artifacts=bool(mlflow.get("log_artifacts", True)),
    )


def parse_args(argv: list[str] | None = None) -> Any:
    import argparse

    parser = argparse.ArgumentParser(description="Run the DVC-configured QA evaluation")
    parser.add_argument("--params", type=Path, default=Path(__file__).with_name("params.yaml"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    params_path = args.params.resolve()
    os.chdir(PROJECT_ROOT)
    result = run_qa_evaluation(load_qa_eval_config(params_path))
    print(
        json.dumps(
            {
                "eval_id": result["eval_id"],
                "question_set_id": result["question_set_id"],
                "question_count": result["question_count"],
                "success_count": result["success_count"],
                "error_count": result["error_count"],
                "metrics": result["metrics"]["overall"],
                "eval_manifest_path": result["eval_manifest_path"],
                "mlflow": result["mlflow"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
