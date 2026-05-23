from fastapi import APIRouter
from neo4j import GraphDatabase
import os


router = APIRouter()


def get_driver():
    uri = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "medgraphrag-password")
    return GraphDatabase.driver(uri, auth=(username, password))


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

    nodes_by_id = {}
    relationships = []

    driver = get_driver()

    try:
        with driver.session() as session:
            results = session.run(query)

            for record in results:
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

    finally:
        driver.close()