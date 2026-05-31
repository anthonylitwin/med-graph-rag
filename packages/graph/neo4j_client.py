import os
from contextlib import contextmanager
from typing import Iterator

from neo4j import GraphDatabase, Driver
from dotenv import load_dotenv


load_dotenv()


def get_neo4j_uri() -> str:
    """
    Use NEO4J_LOCAL_URI when running scripts from the host machine.
    Use NEO4J_URI when running inside Docker.
    """
    return os.getenv("NEO4J_LOCAL_URI") or os.getenv("NEO4J_URI", "bolt://localhost:7687")


def get_neo4j_auth() -> tuple[str, str]:
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "medgraphrag-password")
    return username, password


def get_driver() -> Driver:
    uri = get_neo4j_uri()
    username, password = get_neo4j_auth()
    return GraphDatabase.driver(uri, auth=(username, password))


@contextmanager
def neo4j_driver() -> Iterator[Driver]:
    driver = get_driver()
    try:
        yield driver
    finally:
        driver.close()