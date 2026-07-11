from __future__ import annotations

import functools
import os
from typing import Any, Callable, TypeVar

import redis
from neo4j import GraphDatabase

from app.core.logging import get_logger
from app.services.gpu_utils import check_gpu_available

logger = get_logger("rag.worker.health")

F = TypeVar("F", bound=Callable[..., Any])


def _redis() -> redis.Redis:
    url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    return redis.from_url(url)


def _check_neo4j() -> None:
    uri = os.environ.get("NEO4J_URI", "bolt://neo4j:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "P@ssw0rd")
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        driver.verify_connectivity()
    finally:
        driver.close()


def _check_redis() -> None:
    if not _redis().ping():
        raise RuntimeError("Redis ping failed")


def run_health_checks() -> None:
    _check_neo4j()
    _check_redis()
    check_gpu_available()


def check_health(fn: F) -> F:
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        run_health_checks()
        return fn(*args, **kwargs)

    return wrapper  # type: ignore[return-value]
