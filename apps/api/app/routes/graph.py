from typing import Any

from fastapi import APIRouter, HTTPException, Query
from neo4j import GraphDatabase
import os


router = APIRouter()

ALLOWED_NODE_LABELS = {
    "Paper",
    "Drug",
    "Condition",
    "Symptom",
    "RiskFactor",
    "Biomarker",
}

ALLOWED_RELATIONSHIP_TYPES = {
    "TREATS",
    "PREVENTS",
    "REDUCES",
    "INCREASES",
    "ASSOCIATED_WITH",
    "HAS_ADVERSE_EFFECT",
    "CAUSES",
    "HAS_SYMPTOM",
    "INCREASES_RISK_OF",
    "INTERACTS_WITH",
    "CONTRAINDICATED_FOR",
    "MENTIONS",
    "MAY_INTERACT_WITH",
    "MAY_INCREASE_RISK_OF",
    "MAY_REDUCE",
}


def get_driver():
    uri = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "medgraphrag-password")
    return GraphDatabase.driver(uri, auth=(username, password))


def _graph_response_from_records(records: list[Any]) -> dict:
    nodes_by_id = {}
    relationships = []

    for record in records:
        source_id = record["sourceId"]
        target_id = record["targetId"]

        nodes_by_id[source_id] = {
            "id": source_id,
            "labels": record["sourceLabels"],
            "properties": record["sourceProperties"],
        }

        nodes_by_id[target_id] = {
            "id": target_id,
            "labels": record["targetLabels"],
            "properties": record["targetProperties"],
        }

        relationships.append(
            {
                "source": source_id,
                "target": target_id,
                "type": record["relationshipType"],
                "properties": record["relationshipProperties"],
            }
        )

    return {
        "nodes": list(nodes_by_id.values()),
        "relationships": relationships,
    }


def _validate_label(label: str | None) -> str | None:
    if label is None or label == "":
        return None
    if label not in ALLOWED_NODE_LABELS:
        raise HTTPException(status_code=400, detail=f"Unsupported graph label: {label}")
    return label


def _validate_relationship_type(relationship_type: str | None) -> str | None:
    if relationship_type is None or relationship_type == "":
        return None
    normalized = relationship_type.upper()
    if normalized not in ALLOWED_RELATIONSHIP_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported graph relationship type: {relationship_type}",
        )
    return normalized


@router.get("/sample")
def get_sample_graph() -> dict:
    query = """
    MATCH (source)-[relationship]->(target)
    WHERE source.sample = true AND target.sample = true
    RETURN
        elementId(source) AS sourceId,
        labels(source) AS sourceLabels,
        properties(source) AS sourceProperties,
        type(relationship) AS relationshipType,
        properties(relationship) AS relationshipProperties,
        elementId(target) AS targetId,
        labels(target) AS targetLabels,
        properties(target) AS targetProperties
    ORDER BY sourceProperties.name, sourceProperties.title, relationshipType
    """

    driver = get_driver()

    try:
        with driver.session() as session:
            return _graph_response_from_records(list(session.run(query)))

    finally:
        driver.close()


@router.get("/browse")
def browse_graph(
    q: str | None = Query(default=None, min_length=1, max_length=100),
    label: str | None = Query(default=None),
    relationship_type: str | None = Query(default=None, alias="relationshipType"),
    pmcid: str | None = Query(default=None, min_length=1, max_length=40),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict:
    node_label = _validate_label(label)
    rel_type = _validate_relationship_type(relationship_type)
    normalized_query = q.strip().lower() if q and q.strip() else None
    normalized_pmcid = pmcid.strip() if pmcid and pmcid.strip() else None
    relationship_limit = min(limit * 3, 200)

    query = """
    MATCH (candidate)
    WHERE
        ($label IS NULL OR $label IN labels(candidate))
        AND (
            $q IS NULL
            OR toLower(coalesce(candidate.name, "")) CONTAINS $q
            OR toLower(coalesce(candidate.title, "")) CONTAINS $q
            OR toLower(coalesce(candidate.pmcid, "")) CONTAINS $q
            OR toLower(coalesce(candidate.pmid, "")) CONTAINS $q
            OR toLower(coalesce(candidate.id, "")) CONTAINS $q
        )
        AND (
            $pmcid IS NULL
            OR candidate.pmcid = $pmcid
            OR EXISTS {
                MATCH (:Paper {pmcid: $pmcid})-[:MENTIONS]->(candidate)
            }
        )
    WITH candidate
    ORDER BY coalesce(candidate.name, candidate.title, candidate.pmcid, candidate.id, "")
    LIMIT $limit
    WITH collect(candidate) AS candidates
    CALL {
        WITH candidates
        UNWIND candidates AS candidate
        OPTIONAL MATCH (candidate)-[relationship]-(neighbor)
        WHERE $relationship_type IS NULL OR type(relationship) = $relationship_type
        WITH relationship, neighbor
        WHERE relationship IS NOT NULL
        RETURN collect({
            sourceId: elementId(startNode(relationship)),
            targetId: elementId(endNode(relationship)),
            type: type(relationship),
            properties: properties(relationship),
            neighbor: neighbor
        })[0..$relationship_limit] AS relationshipRows
    }
    WITH candidates + [row IN relationshipRows | row.neighbor] AS allNodes, relationshipRows
    UNWIND allNodes AS node
    WITH DISTINCT node, relationshipRows
    RETURN
        collect({
            id: elementId(node),
            labels: labels(node),
            properties: properties(node)
        })[0..$node_limit] AS nodes,
        relationshipRows
    """

    driver = get_driver()

    try:
        with driver.session() as session:
            record = session.run(
                query,
                label=node_label,
                q=normalized_query,
                relationship_type=rel_type,
                pmcid=normalized_pmcid,
                limit=limit,
                node_limit=limit + relationship_limit,
                relationship_limit=relationship_limit,
            ).single()

        nodes = record["nodes"] if record else []
        relationship_rows = record["relationshipRows"] if record else []
        relationships = [
            {
                "source": row["sourceId"],
                "target": row["targetId"],
                "type": row["type"],
                "properties": row["properties"],
            }
            for row in relationship_rows
        ]

        return {
            "nodes": nodes,
            "relationships": relationships,
            "metadata": {
                "q": normalized_query,
                "label": node_label,
                "relationshipType": rel_type,
                "pmcid": normalized_pmcid,
                "limit": limit,
                "nodeCount": len(nodes),
                "relationshipCount": len(relationships),
            },
        }

    finally:
        driver.close()
