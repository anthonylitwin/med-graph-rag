from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from pipelines.annotation.review_workbook import ReviewWorkbook
from pipelines.annotation.workbook import ENTITY_HEADERS, RELATIONSHIP_HEADERS


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _exportable(row: dict[str, Any], headers: list[str]) -> dict[str, Any]:
    return {header: row.get(header, "") for header in headers}


def _write_csv(path: Path, headers: list[str], rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    return path


def accepted_entity_rows(review: ReviewWorkbook) -> list[dict[str, Any]]:
    return [_exportable(row, ENTITY_HEADERS) for row in review.gold_entities if _clean(row.get("annotation_status")) == "accepted"]


def accepted_relationship_rows(review: ReviewWorkbook) -> list[dict[str, Any]]:
    return [
        _exportable(row, RELATIONSHIP_HEADERS)
        for row in review.gold_relationships
        if _clean(row.get("annotation_status")) == "accepted" and _clean(row.get("annotation_decision")) == "include"
    ]


def write_gold_exports(review: ReviewWorkbook, output_root: Path) -> dict[str, Any]:
    entities = accepted_entity_rows(review)
    relationships = accepted_relationship_rows(review)
    entity_path = _write_csv(output_root / "gold_entities.csv", ENTITY_HEADERS, entities)
    relationship_path = _write_csv(output_root / "gold_relationships.csv", RELATIONSHIP_HEADERS, relationships)
    return {
        "gold_entities_path": entity_path.as_posix(),
        "gold_relationships_path": relationship_path.as_posix(),
        "gold_entity_count": len(entities),
        "gold_relationship_count": len(relationships),
    }


__all__ = ["accepted_entity_rows", "accepted_relationship_rows", "write_gold_exports"]
