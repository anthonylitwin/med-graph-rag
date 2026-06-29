from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipelines.annotation.adjudication import AdjudicationConfig, DEFAULT_GOLD_OUTPUT_ROOT, run_adjudication


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Adjudicate a reviewed MedGraphRAG annotation workbook into gold exports")
    parser.add_argument("--workbook", type=Path, required=True, help="Existing annotation_workbook.xlsx to review/export")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_GOLD_OUTPUT_ROOT)
    parser.add_argument("--review-id", help="Stable review id. Defaults to review-YYYYmmddHHMMSS.")
    parser.add_argument("--force", action="store_true", help="Allow writing into an existing review output directory")
    parser.add_argument("--llm-review", action="store_true", help="Run frontier/OpenAI chunk-by-chunk LLM adjudication before export")
    parser.add_argument("--model", help="Override the configured frontier OpenAI adjudication model")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        report = run_adjudication(
            AdjudicationConfig(
                workbook_path=args.workbook,
                output_root=args.output_root,
                review_id=args.review_id,
                force=args.force,
                llm_review=args.llm_review,
                model=args.model,
            )
        )
    except Exception as exc:
        print(f"Annotation adjudication failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if report["exported"]:
        print(
            "Adjudicated annotation workbook. "
            f"Gold entities: {report['gold_entity_count']}. "
            f"Gold relationships: {report['gold_relationship_count']}. "
            f"Report: {report['adjudication_report_path']}"
        )
        return

    error_count = len(report["validation"]["errors"])
    print(
        "Annotation adjudication completed, but gold export is blocked "
        f"by {error_count} validation error(s). "
        f"Report: {report['adjudication_report_path']}",
        file=sys.stderr,
    )
    raise SystemExit(2)


if __name__ == "__main__":
    main()
