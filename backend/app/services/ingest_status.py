from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import redis

from app.core.config import get_settings
from app.models.file_schemas import IndexStatus

INGEST_STATUS_PREFIX = "ingest:status:"
INGEST_STATUS_TTL = 86_400


def _redis() -> redis.Redis:
    return redis.from_url(get_settings().redis_url)


def _key(path: str) -> str:
    return f"{INGEST_STATUS_PREFIX}{path}"


def set_pending(path: str, job_id: str) -> None:
    payload = {
        "index_status": "pending",
        "last_ingest_job_id": job_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _redis().setex(_key(path), INGEST_STATUS_TTL, json.dumps(payload))


def set_indexed(path: str, job_id: str, *, chunk_count: int) -> None:
    payload = {
        "index_status": "indexed",
        "last_ingest_job_id": job_id,
        "chunk_count": chunk_count,
        "indexed_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _redis().setex(_key(path), INGEST_STATUS_TTL, json.dumps(payload))


def set_error(path: str, job_id: str, error: str) -> None:
    payload = {
        "index_status": "error",
        "last_ingest_job_id": job_id,
        "error": error[:500],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _redis().setex(_key(path), INGEST_STATUS_TTL, json.dumps(payload))


def get_status(path: str) -> dict[str, Any] | None:
    raw = _redis().get(_key(path))
    if not raw:
        return None
    return json.loads(raw)


def resolve_index_status(path: str, *, neo4j_knowledge: dict[str, Any] | None) -> dict[str, Any]:
    redis_status = get_status(path)
    if redis_status:
        status = redis_status.get("index_status", "not_indexed")
        if status == "pending":
            return {
                "index_status": "pending",
                "last_ingest_job_id": redis_status.get("last_ingest_job_id"),
                "chunk_count": int(redis_status.get("chunk_count") or 0),
                "indexed_at": redis_status.get("indexed_at"),
            }
        if status == "error":
            return {
                "index_status": "error",
                "last_ingest_job_id": redis_status.get("last_ingest_job_id"),
                "chunk_count": int(redis_status.get("chunk_count") or 0),
                "indexed_at": redis_status.get("indexed_at"),
            }

    if neo4j_knowledge:
        indexed_at = neo4j_knowledge.get("indexed_at")
        if indexed_at is not None and not isinstance(indexed_at, str):
            indexed_at = str(indexed_at)
        return {
            "index_status": "indexed",
            "last_ingest_job_id": (redis_status or {}).get("last_ingest_job_id"),
            "chunk_count": int(neo4j_knowledge.get("chunk_count") or 0),
            "indexed_at": indexed_at or (redis_status or {}).get("indexed_at"),
        }

    if redis_status and redis_status.get("index_status") == "indexed":
        return {
            "index_status": "indexed",
            "last_ingest_job_id": redis_status.get("last_ingest_job_id"),
            "chunk_count": int(redis_status.get("chunk_count") or 0),
            "indexed_at": redis_status.get("indexed_at"),
        }

    return {
        "index_status": "not_indexed",
        "last_ingest_job_id": None,
        "chunk_count": 0,
        "indexed_at": None,
    }
