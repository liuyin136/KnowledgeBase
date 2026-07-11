from __future__ import annotations

from typing import Any


class IngestBlockedError(Exception):
    """Raised when a source path is not allowed to be ingested into Neo4j."""


class Neo4jError(Exception):
    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        stage: str = "neo4j",
    ) -> None:
        super().__init__(message)
        self.details = details or {}
        self.stage = stage
