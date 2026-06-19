from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from packages.llm.profiles import resolve_model_profile
from pipelines.annotation.workbook import export_annotation_workbook
from pipelines.ingestion.models import (
    DEFAULT_CHUNK_MAX_CHARS,
    DEFAULT_CHUNK_OVERLAP_CHARS,
    PipelineConfig,
)
from pipelines.ingestion.pmc_inputs import collect_pmcids
from pipelines.ingestion.pipeline import process_pmc_articles


DEFAULT_ANNOTATION_OUTPUT_ROOT = Path("data/annotations/bootstrap_v001")
DEFAULT_ANNOTATION_MODEL_PROFILE = "local-qwen25"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap silver MedGraphRAG annotations for human Excel review")
    parser.add_argument(
        "--pmcid",
        action="append",
        nargs="+",
        dest="pmcid_groups",
        help="PMC article id. Can be repeated or space-separated: --pmcid PMC123 PMC456",
    )
    parser.add_argument("--pmcid-file", type=Path, help="Plain text file with one PMCID per line")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_ANNOTATION_OUTPUT_ROOT)
    parser.add_argument("--clean-output", action="store_true", help="Delete output root before creating this run")
    parser.add_argument("--chunk-max-chars", type=int, default=DEFAULT_CHUNK_MAX_CHARS)
    parser.add_argument("--chunk-overlap-chars", type=int, default=DEFAULT_CHUNK_OVERLAP_CHARS)
    parser.add_argument("--model-profile", default=DEFAULT_ANNOTATION_MODEL_PROFILE)
    parser.add_argument("--model", help="Override the profile extraction or local relation model")
    parser.add_argument("--entity-model", help="Override the GLiNER entity model for local extraction")
    parser.add_argument("--min-confidence", type=float, default=0.5)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    return parser.parse_args(argv)


def _write_top_level_manifest(run_root: Path, rows: list[dict[str, Any]]) -> Path:
    manifest_path = run_root / "manifest.csv"
    if not rows:
        manifest_path.write_text("", encoding="utf-8")
        return manifest_path
    fieldnames = list(rows[0].keys())
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return manifest_path


def _read_processed_records(results: list[Any]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    records: list[dict[str, Any]] = []
    processed_paths: dict[str, str] = {}
    for result in results:
        path = Path(result.processed_path)
        if not path.exists():
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        records.append(record)
        document = record.get("document") if isinstance(record.get("document"), dict) else {}
        document_id = str(document.get("id") or "")
        pmcid = str(document.get("pmcid") or result.pmcid or "")
        if document_id:
            processed_paths[document_id] = path.as_posix()
        if pmcid:
            processed_paths[pmcid] = path.as_posix()
    return records, processed_paths


def run_bootstrap(args: argparse.Namespace) -> dict[str, Any]:
    if args.clean_output and args.output_root.exists():
        shutil.rmtree(args.output_root)

    run_id = datetime.now(UTC).strftime("annotation-%Y%m%d%H%M%S")
    run_root = args.output_root / run_id
    if run_root.exists() and not args.force:
        raise RuntimeError(f"Annotation run directory already exists: {run_root}")

    source_root = run_root / "source_documents"
    model_call_root = run_root / "model_calls"
    run_root.mkdir(parents=True, exist_ok=True)

    profile = resolve_model_profile(
        args.model_profile or DEFAULT_ANNOTATION_MODEL_PROFILE,
        extractor_model=args.model,
        entity_model=args.entity_model,
    )
    pmcids = collect_pmcids(args.pmcid_groups, args.pmcid_file, args.limit)
    config = PipelineConfig(
        pmcids=pmcids,
        output_root=source_root,
        clean_output=False,
        chunk_max_chars=args.chunk_max_chars,
        chunk_overlap_chars=args.chunk_overlap_chars,
        model_profile=profile.name,
        extractor_provider=profile.extractor_provider,
        model=profile.extractor_model,
        entity_model=profile.entity_model,
        min_confidence=args.min_confidence,
        skip_load=True,
        force=args.force,
        fail_fast=args.fail_fast,
        model_call_root=model_call_root,
    )

    results = process_pmc_articles(config)
    records, processed_paths = _read_processed_records(results)
    workbook_path = export_annotation_workbook(
        records,
        run_root / "annotation_workbook.xlsx",
        processed_paths=processed_paths,
    )
    manifest_rows = [result.manifest_row() for result in results]
    manifest_path = _write_top_level_manifest(run_root, manifest_rows)

    run_manifest = {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "mode": "annotation_bootstrap",
        "annotation_level": "silver",
        "model_profile": profile.to_dict(),
        "pmcids": pmcids,
        "source_documents_root": source_root.as_posix(),
        "model_calls_root": model_call_root.as_posix(),
        "workbook_path": workbook_path.as_posix(),
        "manifest_path": manifest_path.as_posix(),
        "article_count": len(results),
        "processed_record_count": len(records),
        "success_count": sum(1 for result in results if result.status == "ok"),
        "results": manifest_rows,
    }
    run_manifest_path = run_root / "run_manifest.json"
    run_manifest_path.write_text(json.dumps(run_manifest, indent=2), encoding="utf-8")
    run_manifest["run_manifest_path"] = run_manifest_path.as_posix()
    return run_manifest


def main(argv: list[str] | None = None) -> None:
    manifest = run_bootstrap(parse_args(argv))
    print(
        "Bootstrapped "
        f"{manifest['success_count']}/{manifest['article_count']} article(s). "
        f"Workbook: {manifest['workbook_path']}"
    )


if __name__ == "__main__":
    main()
