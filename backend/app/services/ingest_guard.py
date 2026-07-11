"""Guards against ingesting blocked source paths into Neo4j."""
from __future__ import annotations

import os

from app.core.exceptions import IngestBlockedError

BLOCKED_INGEST_PREFIXES = ("_benchmark/",)


def benchmark_ingest_allowed() -> bool:
    return os.environ.get("ALLOW_BENCHMARK_INGEST") == "1"


def is_blocked_source(relative_path: str) -> bool:
    if not relative_path:
        return False
    if relative_path.startswith("_benchmark/") and benchmark_ingest_allowed():
        return False
    return any(relative_path.startswith(p) for p in BLOCKED_INGEST_PREFIXES)


def assert_ingestible_source(relative_path: str) -> None:
    if is_blocked_source(relative_path):
        raise IngestBlockedError(f"Ingest blocked for path: {relative_path}")
