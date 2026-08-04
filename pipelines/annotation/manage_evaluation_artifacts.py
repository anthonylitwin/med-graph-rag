from __future__ import annotations

import argparse
import csv
import fnmatch
import hashlib
import json
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVAL_ROOT = PROJECT_ROOT / "data" / "annotations" / "eval_v001"
DEFAULT_PARAMS_PATH = PROJECT_ROOT / "experiments" / "params.yaml"
PIN_FILENAME = ".keep"
INDEX_JSON_FILENAME = "evaluation_index.json"
INDEX_CSV_FILENAME = "evaluation_index.csv"
REQUIRED_RUN_FILES = (
    "eval_manifest.json",
    "artifact_manifest.json",
    "metrics.json",
    "metrics.csv",
    "summary.md",
    "chunk_results.csv",
    "errors.csv",
)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_datetime(value: Any, fallback: datetime) -> datetime:
    text = str(value or "").strip()
    if text:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            pass
    return fallback.astimezone(UTC)


def _directory_stats(path: Path) -> tuple[int, int]:
    files = [item for item in path.rglob("*") if item.is_file()]
    return len(files), sum(item.stat().st_size for item in files)


def _metric(metrics: dict[str, Any], scope: str, name: str) -> float:
    payload = metrics.get(scope)
    if not isinstance(payload, dict):
        return 0.0
    try:
        return float(payload.get(name, 0.0))
    except (TypeError, ValueError):
        return 0.0


def active_dvc_eval_id(params_path: Path = DEFAULT_PARAMS_PATH) -> str:
    try:
        payload = yaml.safe_load(params_path.read_text(encoding="utf-8")) or {}
    except (FileNotFoundError, yaml.YAMLError):
        return ""
    settings = payload.get("annotation_eval") if isinstance(payload, dict) else None
    return str(settings.get("eval_id") or "").strip() if isinstance(settings, dict) else ""


@dataclass(frozen=True, slots=True)
class EvaluationRunRecord:
    eval_id: str
    path: str
    created_at: str
    updated_at: str
    model_profile: str
    extractor_provider: str
    extractor_model: str
    gold_set_id: str
    chunk_count: int
    success_count: int
    error_count: int
    entity_f1: float
    relationship_f1: float
    overall_f1: float
    file_count: int
    size_bytes: int
    status: str
    pinned: bool
    active_dvc: bool
    mlflow_run_id: str


def inspect_run(run_root: Path, *, active_eval_id: str = "") -> EvaluationRunRecord:
    manifest = _read_json(run_root / "eval_manifest.json")
    metrics = _read_json(run_root / "metrics.json")
    if not metrics and isinstance(manifest.get("metrics"), dict):
        metrics = manifest["metrics"]
    profile = manifest.get("model_profile") if isinstance(manifest.get("model_profile"), dict) else {}
    mlflow = manifest.get("mlflow") if isinstance(manifest.get("mlflow"), dict) else {}
    file_count, size_bytes = _directory_stats(run_root)
    modified = datetime.fromtimestamp(run_root.stat().st_mtime, tz=UTC)
    created = _parse_datetime(manifest.get("created_at"), modified)
    missing = [name for name in REQUIRED_RUN_FILES if not (run_root / name).is_file()]
    status = "complete" if not missing else "incomplete"
    try:
        chunk_count = int(manifest.get("chunk_count", 0))
        success_count = int(manifest.get("success_count", 0))
        error_count = int(manifest.get("error_count", 0))
    except (TypeError, ValueError):
        chunk_count = success_count = error_count = 0
        status = "incomplete"
    return EvaluationRunRecord(
        eval_id=str(manifest.get("eval_id") or run_root.name),
        path=run_root.as_posix(),
        created_at=created.isoformat(),
        updated_at=modified.isoformat(),
        model_profile=str(profile.get("name") or manifest.get("model_profile") or "unknown"),
        extractor_provider=str(profile.get("extractor_provider") or ""),
        extractor_model=str(profile.get("extractor_model") or ""),
        gold_set_id=str(manifest.get("gold_set_id") or ""),
        chunk_count=chunk_count,
        success_count=success_count,
        error_count=error_count,
        entity_f1=_metric(metrics, "entities", "f1"),
        relationship_f1=_metric(metrics, "relationships", "f1"),
        overall_f1=_metric(metrics, "overall", "f1"),
        file_count=file_count,
        size_bytes=size_bytes,
        status=status,
        pinned=(run_root / PIN_FILENAME).exists(),
        active_dvc=run_root.name == active_eval_id,
        mlflow_run_id=str(mlflow.get("run_id") or ""),
    )


def inventory(eval_root: Path = DEFAULT_EVAL_ROOT, *, params_path: Path = DEFAULT_PARAMS_PATH) -> list[EvaluationRunRecord]:
    if not eval_root.exists():
        return []
    active_eval_id = active_dvc_eval_id(params_path)
    records = [
        inspect_run(path, active_eval_id=active_eval_id)
        for path in eval_root.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    ]
    return sorted(records, key=lambda item: (item.created_at, item.eval_id), reverse=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _resolve_artifact_path(run_root: Path, recorded_path: str) -> Path:
    path = Path(recorded_path)
    if path.exists():
        return path
    parts = list(path.parts)
    if run_root.name in parts:
        suffix = parts[parts.index(run_root.name) + 1 :]
        candidate = run_root.joinpath(*suffix)
        if candidate.exists():
            return candidate
    return run_root / path.name


@dataclass(frozen=True, slots=True)
class VerificationResult:
    eval_id: str
    checked: int
    missing: tuple[str, ...]
    mismatched: tuple[str, ...]
    valid: bool


def verify_run(run_root: Path) -> VerificationResult:
    manifest = _read_json(run_root / "artifact_manifest.json")
    artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), list) else []
    missing: list[str] = []
    mismatched: list[str] = []
    checked = 0
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        recorded_path = str(item.get("path") or "")
        expected = str(item.get("sha256") or "").lower()
        resolved = _resolve_artifact_path(run_root, recorded_path)
        if not resolved.is_file():
            missing.append(recorded_path)
            continue
        checked += 1
        if not expected or _sha256(resolved).lower() != expected:
            mismatched.append(recorded_path)
    if not artifacts:
        missing.append("artifact_manifest.json:artifacts")
    return VerificationResult(
        eval_id=run_root.name,
        checked=checked,
        missing=tuple(missing),
        mismatched=tuple(mismatched),
        valid=bool(artifacts) and not missing and not mismatched,
    )


def write_index(
    records: Iterable[EvaluationRunRecord],
    eval_root: Path = DEFAULT_EVAL_ROOT,
) -> tuple[Path, Path]:
    rows = [asdict(record) for record in records]
    eval_root.mkdir(parents=True, exist_ok=True)
    json_path = eval_root / INDEX_JSON_FILENAME
    csv_path = eval_root / INDEX_CSV_FILENAME
    json_path.write_text(json.dumps({"runs": rows}, indent=2), encoding="utf-8")
    fieldnames = list(EvaluationRunRecord.__dataclass_fields__)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return json_path, csv_path


@dataclass(frozen=True, slots=True)
class PruneSelection:
    selected: tuple[EvaluationRunRecord, ...]
    protected: tuple[EvaluationRunRecord, ...]


def select_for_prune(
    records: Iterable[EvaluationRunRecord],
    *,
    smoke: bool = False,
    incomplete: bool = False,
    older_than_days: int | None = None,
    pattern: str = "*",
    keep_latest: int = 0,
    now: datetime | None = None,
) -> PruneSelection:
    if not smoke and not incomplete and older_than_days is None and pattern == "*":
        raise ValueError("Prune requires --smoke, --incomplete, --older-than-days, or a restrictive --match")
    current = now or datetime.now(UTC)
    ordered = sorted(records, key=lambda item: item.created_at, reverse=True)
    candidates: list[EvaluationRunRecord] = []
    protected: list[EvaluationRunRecord] = []
    for record in ordered:
        if record.pinned or record.active_dvc:
            protected.append(record)
            continue
        if not fnmatch.fnmatch(record.eval_id, pattern):
            continue
        if smoke and "smoke" not in record.eval_id.casefold():
            continue
        if incomplete and record.status != "incomplete":
            continue
        if older_than_days is not None:
            created = datetime.fromisoformat(record.created_at)
            if created > current - timedelta(days=older_than_days):
                continue
        candidates.append(record)
    if keep_latest > 0:
        protected.extend(candidates[:keep_latest])
        candidates = candidates[keep_latest:]
    return PruneSelection(tuple(candidates), tuple(protected))


def _format_size(value: int) -> str:
    if value < 1024:
        return f"{value} B"
    if value < 1024**2:
        return f"{value / 1024:.1f} KB"
    return f"{value / 1024**2:.1f} MB"


def _print_records(records: Iterable[EvaluationRunRecord]) -> None:
    rows = list(records)
    headers = ("eval_id", "profile", "status", "chunks", "errors", "entity_f1", "rel_f1", "size", "flags")
    rendered: list[tuple[str, ...]] = []
    for record in rows:
        flags = ",".join(name for name, enabled in (("pinned", record.pinned), ("dvc", record.active_dvc)) if enabled)
        rendered.append(
            (
                record.eval_id,
                record.model_profile,
                record.status,
                str(record.chunk_count),
                str(record.error_count),
                f"{record.entity_f1:.4f}",
                f"{record.relationship_f1:.4f}",
                _format_size(record.size_bytes),
                flags,
            )
        )
    widths = [max(len(headers[index]), *(len(row[index]) for row in rendered)) for index in range(len(headers))] if rendered else [len(item) for item in headers]
    print("  ".join(value.ljust(widths[index]) for index, value in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in rendered:
        print("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))
    print(f"\n{len(rows)} run(s), {_format_size(sum(item.size_bytes for item in rows))}")


def _filter_records(
    records: Iterable[EvaluationRunRecord],
    *,
    pattern: str = "*",
    profile: str = "",
    status: str = "",
) -> list[EvaluationRunRecord]:
    return [
        record
        for record in records
        if fnmatch.fnmatch(record.eval_id, pattern)
        and (not profile or record.model_profile == profile)
        and (not status or record.status == status)
    ]


def _selected_run_roots(eval_root: Path, run_ids: list[str]) -> list[Path]:
    if run_ids:
        roots = [eval_root / run_id for run_id in run_ids]
        missing = [path.name for path in roots if not path.is_dir()]
        if missing:
            raise ValueError(f"Unknown evaluation run(s): {', '.join(missing)}")
        return roots
    return [path for path in eval_root.iterdir() if path.is_dir() and not path.name.startswith(".")]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inventory, verify, pin, and prune annotation evaluation artifacts")
    parser.add_argument("--root", type=Path, default=DEFAULT_EVAL_ROOT)
    parser.add_argument("--params", type=Path, default=DEFAULT_PARAMS_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List evaluation runs and key metrics")
    list_parser.add_argument("--json", action="store_true")
    list_parser.add_argument("--match", default="*", help="Shell-style run ID pattern")
    list_parser.add_argument("--profile", default="")
    list_parser.add_argument("--status", choices=("complete", "incomplete"), default="")

    subparsers.add_parser("index", help="Write JSON and CSV run indexes")

    verify_parser = subparsers.add_parser("verify", help="Verify durable artifact hashes")
    verify_parser.add_argument("run_ids", nargs="*")

    pin_parser = subparsers.add_parser("pin", help="Protect one or more runs from pruning")
    pin_parser.add_argument("run_ids", nargs="+")

    unpin_parser = subparsers.add_parser("unpin", help="Remove explicit prune protection")
    unpin_parser.add_argument("run_ids", nargs="+")

    prune_parser = subparsers.add_parser("prune", help="Plan or execute deletion of selected generated runs")
    prune_parser.add_argument("--smoke", action="store_true", help="Select only run IDs containing 'smoke'")
    prune_parser.add_argument("--incomplete", action="store_true", help="Select only incomplete runs")
    prune_parser.add_argument("--older-than-days", type=int)
    prune_parser.add_argument("--match", default="*", help="Shell-style run ID pattern")
    prune_parser.add_argument("--keep-latest", type=int, default=0)
    prune_parser.add_argument("--execute", action="store_true", help="Delete the selected runs; default is dry-run")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    eval_root = args.root.resolve()
    params_path = args.params.resolve()
    try:
        if args.command in {"list", "index", "prune"}:
            records = inventory(eval_root, params_path=params_path)
        if args.command == "list":
            records = _filter_records(
                records,
                pattern=args.match,
                profile=args.profile,
                status=args.status,
            )
            if args.json:
                print(json.dumps([asdict(record) for record in records], indent=2))
            else:
                _print_records(records)
            return
        if args.command == "index":
            json_path, csv_path = write_index(records, eval_root)
            print(f"Wrote {json_path.as_posix()} and {csv_path.as_posix()}")
            return
        if args.command == "verify":
            results = [verify_run(path) for path in _selected_run_roots(eval_root, args.run_ids)]
            for result in results:
                print(
                    f"{result.eval_id}: {'valid' if result.valid else 'INVALID'} "
                    f"({result.checked} checked, {len(result.missing)} missing, {len(result.mismatched)} mismatched)"
                )
            if not all(result.valid for result in results):
                raise SystemExit(1)
            return
        if args.command in {"pin", "unpin"}:
            for run_root in _selected_run_roots(eval_root, args.run_ids):
                pin_path = run_root / PIN_FILENAME
                if args.command == "pin":
                    pin_path.write_text("Protected from artifact pruning.\n", encoding="utf-8")
                elif pin_path.exists():
                    pin_path.unlink()
                print(f"{args.command}: {run_root.name}")
            return
        if args.command == "prune":
            if args.older_than_days is not None and args.older_than_days < 0:
                raise ValueError("--older-than-days must be non-negative")
            if args.keep_latest < 0:
                raise ValueError("--keep-latest must be non-negative")
            selection = select_for_prune(
                records,
                smoke=args.smoke,
                incomplete=args.incomplete,
                older_than_days=args.older_than_days,
                pattern=args.match,
                keep_latest=args.keep_latest,
            )
            print("Protected:")
            _print_records(selection.protected)
            print("\nSelected for deletion:" if args.execute else "\nDry-run candidates:")
            _print_records(selection.selected)
            if not args.execute:
                print("\nNothing deleted. Re-run with --execute after reviewing the candidates.")
                return
            resolved_root = eval_root.resolve()
            for record in selection.selected:
                target = Path(record.path).resolve()
                if target.parent != resolved_root:
                    raise RuntimeError(f"Refusing to delete path outside evaluation root: {target}")
                shutil.rmtree(target)
                print(f"Deleted {target.name}")
            return
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Artifact management failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()


__all__ = [
    "EvaluationRunRecord",
    "PruneSelection",
    "VerificationResult",
    "active_dvc_eval_id",
    "inspect_run",
    "inventory",
    "select_for_prune",
    "verify_run",
    "write_index",
]
