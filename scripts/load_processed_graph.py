from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipelines.ingestion.neo4j_loader import load_processed_records


REQUIRED_RELATIONSHIP_FIELDS = (
    "source_pmcid",
    "chunk_id",
    "evidence",
    "confidence",
    "extractor",
    "model",
)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Processed artifact must be a JSON object: {path}")
    return payload


def _processed_paths(processed_dir: Path) -> list[Path]:
    paths = sorted(processed_dir.glob("*.json"))
    if not paths:
        raise ValueError(f"No processed JSON files found in {processed_dir}")
    return paths


def _relationship_metadata_report(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = 0
    complete = 0
    missing: dict[str, int] = {field: 0 for field in REQUIRED_RELATIONSHIP_FIELDS}
    for record in records:
        for relationship in record.get("relationships") or []:
            if not isinstance(relationship, dict):
                continue
            properties = relationship.get("properties") if isinstance(relationship.get("properties"), dict) else {}
            total += 1
            missing_fields = [field for field in REQUIRED_RELATIONSHIP_FIELDS if properties.get(field) in (None, "")]
            if missing_fields:
                for field in missing_fields:
                    missing[field] += 1
            else:
                complete += 1
    return {
        "relationship_count": total,
        "complete_relationship_metadata_count": complete,
        "missing_relationship_metadata": {field: count for field, count in missing.items() if count},
        "required_relationship_fields": list(REQUIRED_RELATIONSHIP_FIELDS),
    }


def load_processed_graph(
    *,
    processed_dir: Path,
    graph_run_id: str,
    graph_source: str,
    report_path: Path | None = None,
    apply_schema: bool = False,
) -> dict[str, Any]:
    processed_paths = _processed_paths(processed_dir)
    records = [_read_json(path) for path in processed_paths]
    loaded_at = datetime.now(UTC).isoformat()
    if apply_schema:
        from scripts.apply_neo4j_schema import apply_neo4j_schema

        apply_neo4j_schema()

    counts = load_processed_records(
        records,
        graph_run_id=graph_run_id,
        graph_source=graph_source,
        loaded_at=loaded_at,
    )
    source_run_ids = sorted(
        {
            str((record.get("run") or {}).get("id") or "").strip()
            for record in records
            if isinstance(record.get("run"), dict) and str((record.get("run") or {}).get("id") or "").strip()
        }
    )
    report = {
        "graph_run_id": graph_run_id,
        "graph_source": graph_source,
        "loaded_at": loaded_at,
        "processed_dir": processed_dir.as_posix(),
        "processed_files": [path.as_posix() for path in processed_paths],
        "source_run_ids": source_run_ids,
        "apply_schema": apply_schema,
        "counts": counts,
        "relationship_metadata": _relationship_metadata_report(records),
    }
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load processed extraction artifacts into Neo4j as one graph run")
    parser.add_argument("--processed-dir", type=Path, required=True)
    parser.add_argument("--graph-run-id", required=True)
    parser.add_argument("--graph-source", default="")
    parser.add_argument("--report-path", type=Path)
    parser.add_argument("--apply-schema", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    report = load_processed_graph(
        processed_dir=args.processed_dir,
        graph_run_id=args.graph_run_id,
        graph_source=args.graph_source,
        report_path=args.report_path,
        apply_schema=args.apply_schema,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

