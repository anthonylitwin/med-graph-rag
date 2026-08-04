from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.ingestion_service import get_ingestion_queue_service
from packages.llm.profiles import list_model_profiles


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
    modelProfile: str | None = None
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


@router.post("/jobs")
def create_ingestion_job(request: IngestionJobRequest) -> dict:
    service = get_ingestion_queue_service()
    try:
        job = service.create_job(
            source_type=request.sourceType,
            pmcids=_pmcids_from_request(request),
            text_documents=[_model_payload(document) for document in request.documents],
            model_profile=request.modelProfile,
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
    return {"profiles": [profile.to_dict() for profile in list_model_profiles()]}
