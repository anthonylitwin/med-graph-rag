import os
from neo4j import GraphDatabase


def get_driver():
    uri = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "medgraphrag-password")
    return GraphDatabase.driver(uri, auth=(username, password))


def extract_entity_name(question: str) -> str | None:
    """
    Temporary rule-based entity extraction.

    Later this gets replaced by:
    - LLM extraction
    - biomedical NER
    - UMLS/MeSH normalization
    """
    normalized = question.lower()

    if "aspirin" in normalized:
        return "Aspirin"

    return None


def get_entity_relationships(entity_name: str) -> list[dict]:
    # OPTIONAL MATCH (chunk:Chunk)-[:MENTIONS]->(entity)
    # OPTIONAL MATCH (doc:Document)-[:HAS_CHUNK]->(chunk)
    # ,
    #     doc.id AS documentId,
    #     doc.title AS documentTitle
    query = """
    MATCH (n:Drug {name: $entity_name})-[relationship]->(target:Condition)
    RETURN
        n.name AS sourceName,
        labels(n) AS sourceLabels,
        type(relationship) AS relationshipType,
        relationship.evidence_text AS evidenceText,
        relationship.confidence AS confidence,
        target.name AS targetName,
        labels(target) AS targetLabels
    ORDER BY relationshipType, targetName
    """

    driver = get_driver()

    try:
        with driver.session() as session:
            results = session.run(query, entity_name=entity_name)
            return [dict(record) for record in results]
    finally:
        driver.close()


def relationship_to_sentence(row: dict) -> str:
    source = row["sourceName"]
    target = row["targetName"]
    relationship = row["relationshipType"]

    if relationship == "MAY_INTERACT_WITH":
        return f"{source} may interact with {target}."

    if relationship == "MAY_INCREASE_RISK_OF":
        return f"{source} may increase the risk of {target}."

    if relationship == "MAY_REDUCE":
        return f"{source} may reduce {target}."

    if relationship == "TREATS":
        return f"{source} treats {target}."

    return f"{source} is connected to {target} by {relationship}."


def answer_question(question: str) -> dict:
    entity_name = extract_entity_name(question)

    if entity_name is None:
        return {
            "answer": (
                "I could not identify a known biomedical entity in the question yet. "
                "Try asking about Aspirin."
            ),
            "sources": [],
            "reasoningPath": [],
            "model": "graph-rag-rule-based-v0",
        }

    relationships = get_entity_relationships(entity_name)

    if not relationships:
        return {
            "answer": f"I found {entity_name}, but no graph relationships are available yet.",
            "sources": [],
            "reasoningPath": [],
            "model": "graph-rag-rule-based-v0",
        }

    answer_sentences = [relationship_to_sentence(row) for row in relationships]

    sources = []
    reasoning_path = []

    for row in relationships:
        sources.append(
            {
                "documentId": row.get("documentId"),
                "title": row.get("documentTitle"),
                "evidenceText": row.get("evidenceText"),
                "confidence": row.get("confidence"),
            }
        )

        reasoning_path.append(
            {
                "source": row.get("sourceName"),
                "relationship": row.get("relationshipType"),
                "target": row.get("targetName"),
            }
        )

    return {
        "answer": " ".join(answer_sentences),
        "sources": sources,
        "reasoningPath": reasoning_path,
        "model": "graph-rag-rule-based-v0",
    }