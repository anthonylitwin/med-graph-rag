from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.services.ingestion_service import get_ingestion_queue_service
from app.services.qa_service import get_active_model_runtime


router = APIRouter()


class TextDocumentPayload(BaseModel):
    title: str | None = None
    text: str
    sourceName: str | None = None


class IngestionJobRequest(BaseModel):
    sourceType: Literal["pmc", "text"] = "pmc"
    pmcids: list[str] = []
    pmcidText: str | None = None
    documents: list[TextDocumentPayload] = []
    applySchema: bool = False
    skipLoad: bool = False
    failFast: bool = False


def _pmcids_from_request(request: IngestionJobRequest) -> list[str]:
    values = list(request.pmcids)
    for raw_line in (request.pmcidText or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        values.extend(part for part in re.split(r"[\s,]+", line) if part)
    return values


def _model_payload(value: BaseModel) -> dict:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value.dict()


async def _raw_model_profile(http_request: Request) -> str | None:
    try:
        payload = await http_request.json()
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(payload, dict):
        return None
    value = payload.get("modelProfile")
    return str(value) if value is not None else None


@router.post("/jobs")
async def create_ingestion_job(request: IngestionJobRequest, http_request: Request) -> dict:
    service = get_ingestion_queue_service()
    try:
        job = service.create_job(
            source_type=request.sourceType,
            pmcids=_pmcids_from_request(request),
            text_documents=[_model_payload(document) for document in request.documents],
            model_profile=await _raw_model_profile(http_request),
            apply_schema=request.applySchema,
            skip_load=request.skipLoad,
            fail_fast=request.failFast,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return job


@router.get("/jobs")
def list_ingestion_jobs(limit: int = Query(default=50, ge=1, le=200)) -> dict:
    service = get_ingestion_queue_service()
    return {"jobs": service.list_jobs(limit=limit)}


@router.get("/jobs/{job_id}")
def get_ingestion_job(job_id: str) -> dict:
    service = get_ingestion_queue_service()
    job = service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Ingestion job not found: {job_id}")
    return job


@router.get("/jobs/{job_id}/artifacts")
def get_ingestion_artifacts(job_id: str) -> dict:
    service = get_ingestion_queue_service()
    artifacts = service.get_artifacts(job_id)
    if artifacts is None:
        raise HTTPException(status_code=404, detail=f"Ingestion job not found: {job_id}")
    return artifacts


@router.post("/jobs/{job_id}/cancel")
def cancel_ingestion_job(job_id: str) -> dict:
    service = get_ingestion_queue_service()
    canceled = service.cancel_job(job_id)
    if not canceled:
        raise HTTPException(status_code=409, detail="Only queued jobs can be canceled")
    job = service.get_job(job_id)
    return job or {"id": job_id, "status": "canceled"}


@router.get("/model-options")
def ingestion_model_options() -> dict:
    return get_active_model_runtime()
