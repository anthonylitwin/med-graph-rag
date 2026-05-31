from pathlib import Path
import sys

# Ensure project root is importable regardless of calling shell/interpreter.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from packages.graph.neo4j_client import neo4j_driver


def clear_sample_graph() -> None:
    query = """
    MATCH (n)
    WHERE n.sample = true
    DETACH DELETE n
    """

    with neo4j_driver() as driver:
        with driver.session() as session:
            session.run(query)


def seed_sample_graph() -> None:
    query = """
    MERGE (paper:Paper {id: "sample-paper-001"})
    SET paper.title = "Sample Aspirin Interaction Abstract",
        paper.source = "local-sample",
        paper.sample = true,
        paper.abstract = "Aspirin is commonly used to reduce pain, fever, or inflammation. It may interact with anticoagulant medications and can increase bleeding risk."

    MERGE (aspirin:Drug {name: "Aspirin"})
    SET aspirin.sample = true

    MERGE (anticoagulant:Drug {name: "Anticoagulant medication"})
    SET anticoagulant.sample = true

    MERGE (bleeding:Condition {name: "Bleeding risk"})
    SET bleeding.sample = true

    MERGE (inflammation:Condition {name: "Inflammation"})
    SET inflammation.sample = true

    MERGE (paper)-[:MENTIONS {sample: true}]->(aspirin)
    MERGE (paper)-[:MENTIONS {sample: true}]->(anticoagulant)
    MERGE (paper)-[:MENTIONS {sample: true}]->(bleeding)
    MERGE (paper)-[:MENTIONS {sample: true}]->(inflammation)

    MERGE (aspirin)-[:MAY_INTERACT_WITH {sample: true}]->(anticoagulant)
    MERGE (aspirin)-[:MAY_INCREASE_RISK_OF {sample: true}]->(bleeding)
    MERGE (aspirin)-[:MAY_REDUCE {sample: true}]->(inflammation)
    """

    with neo4j_driver() as driver:
        with driver.session() as session:
            session.run(query)


def main() -> None:
    clear_sample_graph()
    seed_sample_graph()
    print("Sample biomedical graph seeded successfully.")


if __name__ == "__main__":
    main()