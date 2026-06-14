from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipelines.ingestion.models import (
    DEFAULT_CHUNK_MAX_CHARS,
    DEFAULT_CHUNK_OVERLAP_CHARS,
    DEFAULT_OUTPUT_ROOT,
    PipelineConfig,
)
from packages.llm.profiles import resolve_model_profile
from pipelines.ingestion.pmc_inputs import collect_pmcids
from pipelines.ingestion.pipeline import process_pmc_articles


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch, chunk, extract, and load PMC articles into Neo4j")
    parser.add_argument(
        "--pmcid",
        action="append",
        nargs="+",
        dest="pmcid_groups",
        help="PMC article id. Can be repeated or space-separated: --pmcid PMC123 PMC456",
    )
    parser.add_argument(
        "--pmcid-file",
        type=Path,
        help="Plain text file with one PMCID per line. Blank lines and # comments are ignored.",
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--clean-output", action="store_true", help="Delete output directory before writing artifacts")
    parser.add_argument("--chunk-max-chars", type=int, default=DEFAULT_CHUNK_MAX_CHARS)
    parser.add_argument("--chunk-overlap-chars", type=int, default=DEFAULT_CHUNK_OVERLAP_CHARS)
    parser.add_argument("--model-profile", help="Runtime profile: frontier, local-qwen25, local-qwen3, or noop.")
    parser.add_argument("--extractor", choices=["openai", "gliner_ollama", "noop"], help="Override the profile extractor.")
    parser.add_argument("--model", help="Override the profile extraction or local relation model.")
    parser.add_argument("--entity-model", help="Override the GLiNER entity model for local extraction.")
    parser.add_argument("--min-confidence", type=float, default=0.5)
    parser.add_argument("--apply-schema", action="store_true")
    parser.add_argument("--skip-extract", action="store_true")
    parser.add_argument("--skip-load", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--limit", type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    profile = resolve_model_profile(
        args.model_profile,
        extractor_provider=args.extractor,
        extractor_model=args.model,
        entity_model=args.entity_model,
    )
    pmcids = collect_pmcids(args.pmcid_groups, args.pmcid_file, args.limit)
    config = PipelineConfig(
        pmcids=pmcids,
        output_root=args.output_root,
        clean_output=args.clean_output,
        chunk_max_chars=args.chunk_max_chars,
        chunk_overlap_chars=args.chunk_overlap_chars,
        model_profile=profile.name,
        extractor_provider=profile.extractor_provider,
        model=profile.extractor_model,
        entity_model=profile.entity_model,
        min_confidence=args.min_confidence,
        apply_schema=args.apply_schema,
        skip_extract=args.skip_extract,
        skip_load=args.skip_load,
        force=args.force,
        fail_fast=args.fail_fast,
    )
    results = process_pmc_articles(config)
    success_count = sum(1 for result in results if result.status == "ok")
    manifest_path = args.output_root / "manifest.csv"
    print(f"Processed {success_count}/{len(results)} article(s). Manifest: {manifest_path.as_posix()}")


if __name__ == "__main__":
    main()
