from __future__ import annotations

import json
import os
import sqlite3
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _ensure_repo_root_on_path() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "packages").exists():
            if str(parent) not in sys.path:
                sys.path.insert(0, str(parent))
            return parent
    return Path.cwd()


PROJECT_ROOT = _ensure_repo_root_on_path()

from app.services.qa_service import get_app_model_profile
from packages.llm.profiles import normalize_model_profile_name
from pipelines.ingestion.models import (
    DEFAULT_CHUNK_MAX_CHARS,
    DEFAULT_CHUNK_OVERLAP_CHARS,
    PipelineConfig,
)
from pipelines.ingestion.pipeline import process_pmc_articles
from pipelines.ingestion.pmc_inputs import collect_pmcids
from pipelines.ingestion.text_pipeline import TextDocumentInput, _text_document_key, process_text_documents


TERMINAL_STATUSES = {"completed", "failed", "canceled"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _repo_path_from_env(name: str, default: str) -> Path:
    raw_value = os.getenv(name)
    path = Path(raw_value) if raw_value else Path(default)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def ingestion_db_path() -> Path:
    return _repo_path_from_env("INGESTION_JOB_DB_PATH", "data/ingestion/jobs.sqlite")


def ingestion_output_root() -> Path:
    return _repo_path_from_env("INGESTION_OUTPUT_ROOT", "data/source_documents/ui_ingestion")


class IngestionJobStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or ingestion_db_path()
        self._lock = threading.RLock()
        self.initialize()

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ingestion_jobs (
                    id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    submitted_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    progress_current INTEGER NOT NULL DEFAULT 0,
                    progress_total INTEGER NOT NULL DEFAULT 0,
                    model_profile TEXT NOT NULL,
                    apply_schema INTEGER NOT NULL DEFAULT 0,
                    skip_load INTEGER NOT NULL DEFAULT 0,
                    fail_fast INTEGER NOT NULL DEFAULT 0,
                    output_root TEXT NOT NULL,
                    source_payload TEXT NOT NULL,
                    options_json TEXT NOT NULL,
                    error TEXT NOT NULL DEFAULT ''
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ingestion_job_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    document_key TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    fetch_status TEXT NOT NULL DEFAULT 'pending',
                    extract_status TEXT NOT NULL DEFAULT 'pending',
                    load_status TEXT NOT NULL DEFAULT 'pending',
                    chunk_count INTEGER NOT NULL DEFAULT 0,
                    entity_count INTEGER NOT NULL DEFAULT 0,
                    relationship_count INTEGER NOT NULL DEFAULT 0,
                    error TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(job_id) REFERENCES ingestion_jobs(id)
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def create_job(
        self,
        *,
        source_type: str,
        source_payload: dict[str, Any],
        model_profile: str,
        apply_schema: bool,
        skip_load: bool,
        fail_fast: bool,
        document_keys: list[str],
    ) -> dict[str, Any]:
        job_id = f"ing-{uuid.uuid4().hex[:12]}"
        output_root = ingestion_output_root() / job_id
        options = {
            "model_profile": model_profile,
            "apply_schema": apply_schema,
            "skip_load": skip_load,
            "fail_fast": fail_fast,
        }
        with self._lock, self._connection() as connection:
            connection.execute(
                """
                INSERT INTO ingestion_jobs (
                    id, source_type, status, submitted_at, progress_total,
                    model_profile, apply_schema, skip_load, fail_fast, output_root,
                    source_payload, options_json
                )
                VALUES (?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    source_type,
                    _now(),
                    len(document_keys),
                    model_profile,
                    int(apply_schema),
                    int(skip_load),
                    int(fail_fast),
                    output_root.as_posix(),
                    json.dumps(source_payload),
                    json.dumps(options),
                ),
            )
            connection.executemany(
                """
                INSERT INTO ingestion_job_documents (job_id, document_key, status)
                VALUES (?, ?, 'queued')
                """,
                [(job_id, key) for key in document_keys],
            )
        return self.get_job(job_id) or {}

    def claim_next_job(self) -> dict[str, Any] | None:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM ingestion_jobs
                WHERE status = 'queued'
                ORDER BY submitted_at
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                """
                UPDATE ingestion_jobs
                SET status = 'running', started_at = ?, error = ''
                WHERE id = ? AND status = 'queued'
                """,
                (_now(), row["id"]),
            )
        return self.get_job(str(row["id"]))

    def list_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM ingestion_jobs
                ORDER BY submitted_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._job_from_row(row, include_documents=False) for row in rows]

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM ingestion_jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                return None
            document_rows = connection.execute(
                """
                SELECT * FROM ingestion_job_documents
                WHERE job_id = ?
                ORDER BY id
                """,
                (job_id,),
            ).fetchall()
        return self._job_from_row(row, include_documents=True, document_rows=document_rows)

    def mark_document_running(self, job_id: str, document_key: str) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                """
                UPDATE ingestion_job_documents
                SET status = 'running'
                WHERE job_id = ? AND document_key = ?
                """,
                (job_id, document_key),
            )

    def record_document_result(self, job_id: str, result: Any) -> None:
        status = "completed" if result.status == "ok" else result.status
        with self._lock, self._connection() as connection:
            connection.execute(
                """
                UPDATE ingestion_job_documents
                SET
                    title = ?,
                    status = ?,
                    fetch_status = ?,
                    extract_status = ?,
                    load_status = ?,
                    chunk_count = ?,
                    entity_count = ?,
                    relationship_count = ?,
                    error = ?
                WHERE job_id = ? AND document_key = ?
                """,
                (
                    result.title,
                    status,
                    result.fetch_status,
                    result.extract_status,
                    result.load_status,
                    result.chunk_count,
                    result.entity_count,
                    result.relationship_count,
                    result.error,
                    job_id,
                    result.pmcid,
                ),
            )
            completed = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM ingestion_job_documents
                WHERE job_id = ? AND status IN ('completed', 'failed', 'skipped', 'error')
                """,
                (job_id,),
            ).fetchone()["count"]
            connection.execute(
                """
                UPDATE ingestion_jobs
                SET progress_current = ?
                WHERE id = ?
                """,
                (completed, job_id),
            )

    def finish_job(self, job_id: str, status: str, error: str = "") -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                """
                UPDATE ingestion_jobs
                SET status = ?, finished_at = ?, error = ?
                WHERE id = ?
                """,
                (status, _now(), error, job_id),
            )

    def cancel_job(self, job_id: str) -> bool:
        with self._lock, self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE ingestion_jobs
                SET status = 'canceled', finished_at = ?
                WHERE id = ? AND status = 'queued'
                """,
                (_now(), job_id),
            )
        return cursor.rowcount > 0

    def _job_from_row(
        self,
        row: sqlite3.Row,
        *,
        include_documents: bool,
        document_rows: list[sqlite3.Row] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "id": row["id"],
            "sourceType": row["source_type"],
            "status": row["status"],
            "submittedAt": row["submitted_at"],
            "startedAt": row["started_at"],
            "finishedAt": row["finished_at"],
            "progressCurrent": row["progress_current"],
            "progressTotal": row["progress_total"],
            "modelProfile": row["model_profile"],
            "applySchema": bool(row["apply_schema"]),
            "skipLoad": bool(row["skip_load"]),
            "failFast": bool(row["fail_fast"]),
            "outputRoot": row["output_root"],
            "error": row["error"],
            "options": _json_loads(row["options_json"], {}),
        }
        if include_documents:
            payload["documents"] = [
                {
                    "documentKey": document_row["document_key"],
                    "title": document_row["title"],
                    "status": document_row["status"],
                    "fetchStatus": document_row["fetch_status"],
                    "extractStatus": document_row["extract_status"],
                    "loadStatus": document_row["load_status"],
                    "chunkCount": document_row["chunk_count"],
                    "entityCount": document_row["entity_count"],
                    "relationshipCount": document_row["relationship_count"],
                    "error": document_row["error"],
                }
                for document_row in document_rows or []
            ]
        return payload


class IngestionQueueService:
    def __init__(self, store: IngestionJobStore | None = None, poll_interval_seconds: float = 1.0) -> None:
        self.store = store or IngestionJobStore()
        self.poll_interval_seconds = poll_interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker_loop, name="ingestion-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def create_job(
        self,
        *,
        source_type: str,
        pmcids: list[str] | None = None,
        text_documents: list[dict[str, str]] | None = None,
        model_profile: str | None = None,
        apply_schema: bool = False,
        skip_load: bool = False,
        fail_fast: bool = False,
    ) -> dict[str, Any]:
        normalized_source_type = source_type.strip().lower()
        resolved_profile = self._active_ingestion_profile(model_profile)

        if normalized_source_type == "pmc":
            normalized_pmcids = collect_pmcids([pmcids or []])
            return self.store.create_job(
                source_type="pmc",
                source_payload={"pmcids": normalized_pmcids},
                model_profile=resolved_profile.name,
                apply_schema=apply_schema,
                skip_load=skip_load,
                fail_fast=fail_fast,
                document_keys=normalized_pmcids,
            )

        if normalized_source_type == "text":
            inputs = []
            for index, document in enumerate(text_documents or [], start=1):
                text = str(document.get("text") or "").strip()
                if not text:
                    continue
                title = str(document.get("title") or document.get("sourceName") or f"Uploaded text {index}").strip()
                source_name = str(document.get("sourceName") or "").strip()
                inputs.append({"title": title, "text": text, "sourceName": source_name})
            if not inputs:
                raise ValueError("Provide at least one non-empty text document")
            document_keys = [_text_document_key(item["title"], item["text"]) for item in inputs]
            return self.store.create_job(
                source_type="text",
                source_payload={"documents": inputs},
                model_profile=resolved_profile.name,
                apply_schema=apply_schema,
                skip_load=skip_load,
                fail_fast=fail_fast,
                document_keys=document_keys,
            )

        raise ValueError("sourceType must be 'pmc' or 'text'")

    def list_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.store.list_jobs(limit=limit)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        return self.store.get_job(job_id)

    def get_artifacts(self, job_id: str) -> dict[str, Any] | None:
        job = self.store.get_job(job_id)
        if job is None:
            return None
        root = Path(job["outputRoot"])
        files = []
        if root.exists():
            for path in sorted(item for item in root.rglob("*") if item.is_file()):
                files.append(
                    {
                        "path": path.as_posix(),
                        "relativePath": path.relative_to(root).as_posix(),
                        "size": path.stat().st_size,
                    }
                )
        return {"jobId": job_id, "outputRoot": root.as_posix(), "files": files}

    def cancel_job(self, job_id: str) -> bool:
        return self.store.cancel_job(job_id)

    def run_next_job_once(self) -> bool:
        job = self.store.claim_next_job()
        if job is None:
            return False
        self._run_job(job)
        return True

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            if not self.run_next_job_once():
                self._stop_event.wait(self.poll_interval_seconds)

    def _run_job(self, job: dict[str, Any]) -> None:
        job_id = job["id"]
        try:
            source_payload = self._source_payload(job_id)
            profile = get_app_model_profile()
            config = PipelineConfig(
                pmcids=source_payload.get("pmcids") or [],
                output_root=Path(job["outputRoot"]),
                clean_output=True,
                chunk_max_chars=DEFAULT_CHUNK_MAX_CHARS,
                chunk_overlap_chars=DEFAULT_CHUNK_OVERLAP_CHARS,
                model_profile=profile.name,
                extractor_provider=profile.extractor_provider,
                model=profile.extractor_model,
                entity_model=profile.entity_model,
                apply_schema=bool(job["applySchema"]),
                skip_load=bool(job["skipLoad"]),
                fail_fast=bool(job["failFast"]),
            )

            def progress_callback(event: dict[str, Any]) -> None:
                document_key = str(event.get("pmcid") or "")
                if event.get("event") == "article_started" and document_key:
                    self.store.mark_document_running(job_id, document_key)
                if event.get("event") == "article_finished" and event.get("result") is not None:
                    self.store.record_document_result(job_id, event["result"])

            if job["sourceType"] == "pmc":
                results = process_pmc_articles(config, progress_callback=progress_callback)
            else:
                text_inputs = [
                    TextDocumentInput(
                        title=str(item.get("title") or ""),
                        text=str(item.get("text") or ""),
                        source_name=str(item.get("sourceName") or ""),
                    )
                    for item in source_payload.get("documents", [])
                    if isinstance(item, dict)
                ]
                results = process_text_documents(config, text_inputs, progress_callback=progress_callback)

            final_status = "completed" if all(result.status in {"ok", "skipped"} for result in results) else "failed"
            self.store.finish_job(job_id, final_status)
        except Exception as exc:  # noqa: BLE001
            self.store.finish_job(job_id, "failed", str(exc))

    def _source_payload(self, job_id: str) -> dict[str, Any]:
        with self.store._connection() as connection:
            row = connection.execute(
                "SELECT source_payload FROM ingestion_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"Unknown ingestion job: {job_id}")
        payload = _json_loads(row["source_payload"], {})
        return payload if isinstance(payload, dict) else {}

    def _active_ingestion_profile(self, requested_profile: str | None = None):
        active_profile = get_app_model_profile()
        if requested_profile and requested_profile.strip():
            requested_name = normalize_model_profile_name(requested_profile)
            if requested_name != active_profile.name:
                raise ValueError(
                    "Ingestion uses the server-configured application model profile; "
                    f"got '{requested_profile}', active profile is '{active_profile.name}'."
                )
        return active_profile


_service: IngestionQueueService | None = None


def get_ingestion_queue_service() -> IngestionQueueService:
    global _service
    if _service is None:
        _service = IngestionQueueService()
    return _service
