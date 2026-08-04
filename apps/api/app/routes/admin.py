from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException
from neo4j import GraphDatabase
from pydantic import BaseModel

from app.services.ingestion_service import get_ingestion_queue_service


router = APIRouter()

ACTIVE_INGESTION_STATUSES = {"queued", "running"}
CLEAR_CONFIRMATION = "CLEAR"
DELETE_BATCH_SIZE = 1000


class ClearNeo4jRequest(BaseModel):
    confirmation: str


def get_driver():
    uri = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "medgraphrag-password")
    return GraphDatabase.driver(uri, auth=(username, password))


def _active_ingestion_jobs() -> list[dict[str, Any]]:
    jobs = get_ingestion_queue_service().list_jobs(limit=200)
    return [
        {
            "id": job["id"],
            "status": job["status"],
            "sourceType": job["sourceType"],
            "submittedAt": job["submittedAt"],
        }
        for job in jobs
        if job["status"] in ACTIVE_INGESTION_STATUSES
    ]


def _graph_counts(session: Any) -> dict[str, int]:
    node_record = session.run("MATCH (n) RETURN count(n) AS nodeCount").single()
    relationship_record = session.run("MATCH ()-[r]->() RETURN count(r) AS relationshipCount").single()
    return {
        "nodeCount": int(node_record["nodeCount"] if node_record else 0),
        "relationshipCount": int(relationship_record["relationshipCount"] if relationship_record else 0),
    }


def _neo4j_status_payload(session: Any) -> dict[str, Any]:
    active_jobs = _active_ingestion_jobs()
    return {
        **_graph_counts(session),
        "activeIngestionJobs": active_jobs,
        "canClear": len(active_jobs) == 0,
    }


@router.get("/neo4j/status")
def neo4j_status() -> dict[str, Any]:
    driver = get_driver()
    try:
        with driver.session() as session:
            return _neo4j_status_payload(session)
    finally:
        driver.close()


@router.post("/neo4j/clear")
def clear_neo4j(request: ClearNeo4jRequest) -> dict[str, Any]:
    if request.confirmation != CLEAR_CONFIRMATION:
        raise HTTPException(status_code=400, detail="Type CLEAR to confirm Neo4j deletion")

    driver = get_driver()
    try:
        with driver.session() as session:
            before = _neo4j_status_payload(session)
            if before["activeIngestionJobs"]:
                raise HTTPException(status_code=409, detail="Cannot clear Neo4j while ingestion jobs are active")

            deleted_nodes = 0
            while True:
                record = session.run(
                    """
                    MATCH (n)
                    WITH n LIMIT $batch_size
                    WITH collect(n) AS nodes, count(n) AS deleted
                    FOREACH (node IN nodes | DETACH DELETE node)
                    RETURN deleted
                    """,
                    batch_size=DELETE_BATCH_SIZE,
                ).single()
                deleted = int(record["deleted"] if record else 0)
                deleted_nodes += deleted
                if deleted == 0:
                    break

            after = _graph_counts(session)
            return {
                "before": {
                    "nodeCount": before["nodeCount"],
                    "relationshipCount": before["relationshipCount"],
                },
                "after": after,
                "deletedNodeCount": deleted_nodes,
                "activeIngestionJobs": [],
                "canClear": True,
            }
    finally:
        driver.close()
