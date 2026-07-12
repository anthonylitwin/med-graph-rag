from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pipelines.annotation.manage_evaluation_artifacts import (
    REQUIRED_RUN_FILES,
    inspect_run,
    inventory,
    select_for_prune,
    verify_run,
    write_index,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_run(
    root: Path,
    eval_id: str,
    *,
    created_at: datetime,
    profile: str = "noop",
    pinned: bool = False,
    complete: bool = True,
) -> Path:
    run_root = root / eval_id
    run_root.mkdir(parents=True)
    metrics = {
        "entities": {"f1": 0.4},
        "relationships": {"f1": 0.2},
        "overall": {"f1": 0.3},
    }
    (run_root / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    manifest = {
        "eval_id": eval_id,
        "created_at": created_at.isoformat(),
        "gold_set_id": "fixture-gold",
        "model_profile": {
            "name": profile,
            "extractor_provider": "noop",
            "extractor_model": "fixture-model",
        },
        "chunk_count": 2,
        "success_count": 2,
        "error_count": 0,
        "metrics": metrics,
    }
    (run_root / "eval_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    for filename in REQUIRED_RUN_FILES:
        path = run_root / filename
        if not path.exists() and filename != "artifact_manifest.json":
            path.write_text(f"fixture {filename}\n", encoding="utf-8")
    artifact_path = run_root / "metrics.json"
    artifact_manifest = {
        "artifact_count": 1,
        "artifacts": [
            {
                "path": f"C:/old/workspace/data/annotations/eval_v001/{eval_id}/metrics.json",
                "sha256": _sha256(artifact_path),
            }
        ],
    }
    (run_root / "artifact_manifest.json").write_text(json.dumps(artifact_manifest), encoding="utf-8")
    if not complete:
        (run_root / "summary.md").unlink()
    if pinned:
        (run_root / ".keep").write_text("pinned\n", encoding="utf-8")
    return run_root


class AnnotationArtifactManagementTests(unittest.TestCase):
    def test_inventory_summarizes_metrics_status_size_and_active_dvc_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            params = root / "params.yaml"
            params.write_text("annotation_eval:\n  eval_id: active-run\n", encoding="utf-8")
            _write_run(root, "active-run", created_at=datetime(2026, 1, 2, tzinfo=UTC))
            _write_run(root, "older-smoke", created_at=datetime(2026, 1, 1, tzinfo=UTC), complete=False)

            records = inventory(root, params_path=params)

        self.assertEqual([record.eval_id for record in records], ["active-run", "older-smoke"])
        self.assertTrue(records[0].active_dvc)
        self.assertEqual(records[0].entity_f1, 0.4)
        self.assertEqual(records[0].relationship_f1, 0.2)
        self.assertEqual(records[0].status, "complete")
        self.assertEqual(records[1].status, "incomplete")
        self.assertGreater(records[0].size_bytes, 0)

    def test_verify_resolves_manifest_paths_from_an_old_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_root = _write_run(
                Path(temp_dir),
                "relocated-run",
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
            )

            result = verify_run(run_root)
            (run_root / "metrics.json").write_text("changed\n", encoding="utf-8")
            changed = verify_run(run_root)

        self.assertTrue(result.valid)
        self.assertEqual(result.checked, 1)
        self.assertFalse(changed.valid)
        self.assertEqual(len(changed.mismatched), 1)

    def test_prune_is_selective_and_protects_pinned_and_active_runs(self) -> None:
        now = datetime(2026, 1, 20, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old = _write_run(root, "old-smoke", created_at=now - timedelta(days=10))
            pinned = _write_run(root, "pinned-smoke", created_at=now - timedelta(days=10), pinned=True)
            active = _write_run(root, "active-smoke", created_at=now - timedelta(days=10))
            records = [
                inspect_run(old),
                inspect_run(pinned),
                inspect_run(active, active_eval_id="active-smoke"),
            ]

            selection = select_for_prune(records, smoke=True, older_than_days=5, now=now)

        self.assertEqual([record.eval_id for record in selection.selected], ["old-smoke"])
        self.assertEqual(
            {record.eval_id for record in selection.protected},
            {"pinned-smoke", "active-smoke"},
        )

    def test_write_index_creates_machine_readable_json_and_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_root = _write_run(root, "indexed-run", created_at=datetime(2026, 1, 1, tzinfo=UTC))
            record = inspect_run(run_root)

            json_path, csv_path = write_index([record], root)
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            csv_text = csv_path.read_text(encoding="utf-8")

        self.assertEqual(payload["runs"][0]["eval_id"], "indexed-run")
        self.assertIn("eval_id", csv_text)


if __name__ == "__main__":
    unittest.main()
