from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pipelines.annotation.gold_export import write_gold_exports
from pipelines.annotation.llm_adjudication import run_llm_adjudication
from pipelines.annotation.review_workbook import copy_reviewed_workbook, read_review_workbook
from pipelines.annotation.validation import validate_review_workbook


DEFAULT_GOLD_OUTPUT_ROOT = Path("data/annotations/gold_v001")


@dataclass(frozen=True)
class AdjudicationConfig:
    workbook_path: Path
    output_root: Path = DEFAULT_GOLD_OUTPUT_ROOT
    review_id: str | None = None
    force: bool = False
    llm_review: bool = False
    model_profile: str = "frontier"
    model: str | None = None


def _review_id() -> str:
    return datetime.now(UTC).strftime("review-%Y%m%d%H%M%S")


def _clear_previous_outputs(review_root: Path) -> None:
    for name in [
        "reviewed_annotation_workbook.xlsx",
        "gold_entities.csv",
        "gold_relationships.csv",
        "adjudication_report.json",
    ]:
        path = review_root / name
        if path.exists():
            path.unlink()


def run_adjudication(config: AdjudicationConfig) -> dict[str, Any]:
    source_workbook = config.workbook_path
    review_id = config.review_id or _review_id()
    review_root = config.output_root / review_id
    if review_root.exists() and not config.force:
        raise RuntimeError(f"Adjudication output directory already exists: {review_root}")
    review_root.mkdir(parents=True, exist_ok=True)
    if config.force:
        _clear_previous_outputs(review_root)

    reviewed_workbook_path = copy_reviewed_workbook(source_workbook, review_root / "reviewed_annotation_workbook.xlsx")
    llm_result: dict[str, Any] = {"llm_review": False}
    if config.llm_review:
        llm_result = run_llm_adjudication(
            reviewed_workbook_path,
            review_root,
            model_profile=config.model_profile,
            model=config.model,
        ).to_dict()
    review = read_review_workbook(reviewed_workbook_path)
    validation = validate_review_workbook(review)

    export_result: dict[str, Any] = {"exported": False}
    if validation.valid:
        export_result = {"exported": True, **write_gold_exports(review, review_root)}

    report = {
        "review_id": review_id,
        "created_at": datetime.now(UTC).isoformat(),
        "mode": "annotation_adjudication",
        "source_workbook_path": source_workbook.as_posix(),
        "reviewed_workbook_path": reviewed_workbook_path.as_posix(),
        "output_root": review_root.as_posix(),
        "llm_review": config.llm_review,
        "llm_adjudication": llm_result,
        **export_result,
        "validation": validation.to_dict(),
    }
    report_path = review_root / "adjudication_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["adjudication_report_path"] = report_path.as_posix()
    return report


__all__ = ["AdjudicationConfig", "DEFAULT_GOLD_OUTPUT_ROOT", "run_adjudication"]
