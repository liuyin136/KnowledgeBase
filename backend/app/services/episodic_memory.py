"""Redis episodic session records for manual memory saves."""
from __future__ import annotations

import json
from typing import Any

from app.core.config import get_settings
from app.services.job_queue import get_redis_connection

_KEY_PREFIX = "retrieval:session:"


def _key(session_id: str) -> str:
    return f"{_KEY_PREFIX}{session_id}"


def _ttl_sec() -> int:
    return get_settings().episodic_memory_ttl_sec


def save_episodic_session(
    session_id: str,
    *,
    query: str,
    grandchild_ids: list[str],
    memory_key: str,
    span_id: str | None = None,
    retrieval_tree: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "query": query,
        "grandchild_ids": list(grandchild_ids),
        "memory_key": memory_key,
        "retrieval_tree": retrieval_tree or {},
    }
    if span_id:
        payload["span_id"] = span_id

    conn = get_redis_connection()
    conn.setex(_key(session_id), _ttl_sec(), json.dumps(payload, ensure_ascii=False))
    return payload


def load_episodic_session(session_id: str) -> dict[str, Any] | None:
    conn = get_redis_connection()
    raw = conn.get(_key(session_id))
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)


def delete_episodic_session(session_id: str) -> None:
    conn = get_redis_connection()
    conn.delete(_key(session_id))
