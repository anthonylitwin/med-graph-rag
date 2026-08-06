import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from neo4j import GraphDatabase, Driver
from dotenv import load_dotenv


load_dotenv()


def _is_truthy(value: str | None) -> bool:
    return value is not None and value.strip().lower() in {"1", "true", "yes", "on"}


def running_in_docker() -> bool:
    docker_flag = os.getenv("RUNNING_IN_DOCKER")
    if docker_flag is not None:
        return _is_truthy(docker_flag)
    return Path("/.dockerenv").exists()


def get_neo4j_uri() -> str:
    """
    Use NEO4J_LOCAL_URI when running scripts from the host machine.
    Use NEO4J_URI when running inside Docker.
    """
    docker_uri = os.getenv("NEO4J_URI")
    local_uri = os.getenv("NEO4J_LOCAL_URI")
    if running_in_docker() and docker_uri:
        return docker_uri
    return local_uri or docker_uri or "bolt://localhost:7687"


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
