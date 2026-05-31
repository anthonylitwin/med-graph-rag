from pathlib import Path
import sys

# Ensure project root is importable regardless of calling shell/interpreter.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from packages.graph.neo4j_client import neo4j_driver

SCHEMA_DIR = Path("packages/graph/schema")


def split_cypher_statements(cypher_text: str) -> list[str]:
    return [
        statement.strip()
        for statement in cypher_text.split(";")
        if statement.strip()
    ]


def main() -> None:
    schema_files = sorted(SCHEMA_DIR.glob("*.cypher"))

    if not schema_files:
        raise RuntimeError(f"No schema files found in {SCHEMA_DIR}")

    with neo4j_driver() as driver:
        with driver.session() as session:
            for schema_file in schema_files:
                print(f"Applying {schema_file}")
                cypher_text = schema_file.read_text()
                statements = split_cypher_statements(cypher_text)

                for statement in statements:
                    session.run(statement)

    print("Neo4j schema applied successfully.")


if __name__ == "__main__":
    main()
