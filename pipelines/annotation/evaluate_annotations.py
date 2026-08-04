from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipelines.annotation.evaluation import (
    DEFAULT_ANNOTATION_EVAL_OUTPUT_ROOT,
    DEFAULT_GOLD_MANIFEST_PATH,
    NEO4J_LOAD_MODES,
    AnnotationEvaluationConfig,
    run_annotation_evaluation,
)
from pipelines.ingestion.non_instruct import DEFAULT_TERMINOLOGY_PATH


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate annotation extraction against a MedGraphRAG gold set")
    parser.add_argument("--gold-manifest", type=Path, default=DEFAULT_GOLD_MANIFEST_PATH)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_ANNOTATION_EVAL_OUTPUT_ROOT)
    parser.add_argument("--eval-id", help="Stable evaluation id. Defaults to annotation-eval-YYYYmmddHHMMSS.")
    parser.add_argument(
        "--model-profile",
        default="noop",
        help="Runtime profile: frontier, local-qwen25, local-qwen3, local-gliner, local-non-instruct, or noop.",
    )
    parser.add_argument("--model", help="Override the profile extraction or local relation model.")
    parser.add_argument("--entity-model", help="Override the GLiNER entity model for local extraction.")
    parser.add_argument("--embedding-model", help="Override the local non-instruct sentence embedding model.")
    parser.add_argument("--terminology-path", type=Path, default=DEFAULT_TERMINOLOGY_PATH)
    parser.add_argument("--entity-threshold", type=float, default=0.5)
    parser.add_argument("--concept-threshold", type=float, default=0.84)
    parser.add_argument("--relation-threshold", type=float, default=0.66)
    parser.add_argument("--semantic-floor", type=float, default=0.52)
    parser.add_argument("--semantic-weight", type=float, default=0.50)
    parser.add_argument("--cue-weight", type=float, default=0.25)
    parser.add_argument("--proximity-weight", type=float, default=0.10)
    parser.add_argument("--entity-confidence-weight", type=float, default=0.15)
    parser.add_argument("--max-pair-distance", type=int, default=300)
    parser.add_argument("--min-confidence", type=float, default=0.5)
    parser.add_argument("--limit", type=int, help="Limit the number of gold workbook chunks evaluated.")
    parser.add_argument("--force", action="store_true", help="Allow writing into an existing eval output directory")
    parser.add_argument("--fail-fast", action="store_true", help="Stop on the first chunk extraction error")
    parser.add_argument(
        "--neo4j-load-mode",
        choices=sorted(NEO4J_LOAD_MODES),
        default="none",
        help="Reserved Neo4j load mode. Annotation evaluation currently supports only artifact-only mode: none.",
    )
    parser.add_argument("--apply-schema", action="store_true", help="Reserved for a future Neo4j ingestion step")
    parser.add_argument("--neo4j-run-label", default="", help="Reserved for a future Neo4j ingestion step")
    parser.add_argument("--mlflow", action="store_true", help="Log parameters, metrics, and artifacts to MLflow")
    parser.add_argument("--mlflow-tracking-uri", default="http://localhost:5000")
    parser.add_argument("--mlflow-experiment", default="medgraphrag-annotation-eval")
    parser.add_argument("--mlflow-run-name", default="")
    parser.add_argument(
        "--no-mlflow-artifacts",
        action="store_true",
        help="Log MLflow params and metrics but skip artifact upload",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        result = run_annotation_evaluation(
            AnnotationEvaluationConfig(
                gold_manifest_path=args.gold_manifest,
                output_root=args.output_root,
                eval_id=args.eval_id,
                model_profile=args.model_profile,
                model=args.model,
                entity_model=args.entity_model,
                embedding_model=args.embedding_model,
                terminology_path=args.terminology_path,
                entity_threshold=args.entity_threshold,
                concept_threshold=args.concept_threshold,
                relation_threshold=args.relation_threshold,
                semantic_floor=args.semantic_floor,
                semantic_weight=args.semantic_weight,
                cue_weight=args.cue_weight,
                proximity_weight=args.proximity_weight,
                entity_confidence_weight=args.entity_confidence_weight,
                max_pair_distance=args.max_pair_distance,
                min_confidence=args.min_confidence,
                limit=args.limit,
                force=args.force,
                fail_fast=args.fail_fast,
                neo4j_load_mode=args.neo4j_load_mode,
                apply_schema=args.apply_schema,
                neo4j_run_label=args.neo4j_run_label,
                mlflow=args.mlflow,
                mlflow_tracking_uri=args.mlflow_tracking_uri,
                mlflow_experiment=args.mlflow_experiment,
                mlflow_run_name=args.mlflow_run_name,
                mlflow_log_artifacts=not args.no_mlflow_artifacts,
            )
        )
    except Exception as exc:
        print(f"Annotation evaluation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

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
                "summary_path": result["summary_path"],
                "artifact_manifest_path": result["artifact_manifest_path"],
                "mlflow": result["mlflow"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
