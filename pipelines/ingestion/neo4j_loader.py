from __future__ import annotations

from typing import Any

from packages.graph.neo4j_client import neo4j_driver
from pipelines.ingestion.validation import BIOMEDICAL_ENTITY_TYPES, mention_relationship_id


ENTITY_LABELS = {
    "Drug": "Drug",
    "Condition": "Condition",
    "Symptom": "Symptom",
    "RiskFactor": "RiskFactor",
    "Biomarker": "Biomarker",
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
}


def _label(entity_type: str) -> str:
    if entity_type not in ENTITY_LABELS:
        raise ValueError(f"Unsupported entity label: {entity_type}")
    return ENTITY_LABELS[entity_type]


def _relationship_type(relationship_type: str) -> str:
    normalized = relationship_type.upper()
    if normalized not in ALLOWED_RELATIONSHIP_TYPES:
        raise ValueError(f"Unsupported relationship type: {relationship_type}")
    return normalized


def load_processed_record_with_session(session: Any, record: dict[str, Any]) -> dict[str, int]:
    document = record["document"]
    paper_props = {
        "id": document["id"],
        "pmcid": document.get("pmcid") or "",
        "title": document.get("title") or "",
        "authors": document.get("authors") or [],
        "source": document.get("source") or "pmc",
        "source_url": document.get("source_url") or "",
        "text_length": document.get("text_length") or 0,
        "chunk_count": document.get("chunk_count") or len(record.get("chunks") or []),
    }
    for optional_key in ("pmid", "year", "journal", "doi"):
        optional_value = document.get(optional_key)
        if optional_value:
            paper_props[optional_key] = optional_value
    session.run(
        """
        MERGE (paper:Paper {id: $id})
        SET paper += $props
        """,
        id=paper_props["id"],
        props=paper_props,
    )

    entities_loaded = 0
    for entity in record.get("entities") or []:
        if entity.get("type") not in BIOMEDICAL_ENTITY_TYPES:
            continue
        label = _label(entity["type"])
        props = {
            **(entity.get("properties") or {}),
            "id": entity["id"],
            "name": entity["name"],
        }
        session.run(
            f"""
            MERGE (entity:{label} {{id: $id}})
            SET entity += $props
            """,
            id=entity["id"],
            props=props,
        )
        entities_loaded += 1

        mention_id = mention_relationship_id(paper_props["id"], entity["id"], paper_props["pmcid"])
        session.run(
            f"""
            MATCH (paper:Paper {{id: $paper_id}})
            MATCH (entity:{label} {{id: $entity_id}})
            MERGE (paper)-[mention:MENTIONS {{id: $relationship_id}}]->(entity)
            SET mention += $props
            """,
            paper_id=paper_props["id"],
            entity_id=entity["id"],
            relationship_id=mention_id,
            props={
                "id": mention_id,
                "source_pmcid": paper_props["pmcid"],
                "source_pmid": paper_props.get("pmid", ""),
                "extractor": (entity.get("properties") or {}).get("extractor", ""),
                "model": (entity.get("properties") or {}).get("model", ""),
                "created_at": (entity.get("properties") or {}).get("created_at", ""),
            },
        )

    relationships_loaded = 0
    for relationship in record.get("relationships") or []:
        rel_type = _relationship_type(relationship["type"])
        if rel_type == "MENTIONS":
            continue
        source = relationship["source"]
        target = relationship["target"]
        source_label = _label(source["type"])
        target_label = _label(target["type"])
        props = {
            **(relationship.get("properties") or {}),
            "id": relationship["id"],
        }
        session.run(
            f"""
            MATCH (source:{source_label} {{id: $source_id}})
            MATCH (target:{target_label} {{id: $target_id}})
            MERGE (source)-[relationship:{rel_type} {{id: $relationship_id}}]->(target)
            SET relationship += $props
            """,
            source_id=source["id"],
            target_id=target["id"],
            relationship_id=relationship["id"],
            props=props,
        )
        relationships_loaded += 1

    return {"entities": entities_loaded, "relationships": relationships_loaded}


def load_processed_record(record: dict[str, Any]) -> dict[str, int]:
    with neo4j_driver() as driver:
        with driver.session() as session:
            return load_processed_record_with_session(session, record)
