"""Redis-backed retrieval tree IDs for Phase 2-6 chat memory (no raw text)."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from app.core.config import get_settings
from app.services.job_queue import get_redis_connection

_KEY_PREFIX = "retrieval:tree:"


def _key(session_id: str) -> str:
    return f"{_KEY_PREFIX}{session_id}"


def _ttl_sec() -> int:
    return get_settings().pending_rerank_ttl_sec


def query_hash(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]


def save_retrieval_tree(
    session_id: str,
    *,
    parent_ids: list[str],
    child_ids: list[str],
    grandchild_ids: list[str],
    span_id: str | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "retrieval_tree": {
            "parent_ids": list(dict.fromkeys(parent_ids)),
            "child_ids": list(dict.fromkeys(child_ids)),
            "grandchild_ids": list(dict.fromkeys(grandchild_ids)),
        },
    }
    if span_id:
        payload["span_id"] = span_id
    if query:
        payload["query_hash"] = query_hash(query)

    conn = get_redis_connection()
    conn.setex(_key(session_id), _ttl_sec(), json.dumps(payload, ensure_ascii=False))
    return payload


def load_retrieval_tree(session_id: str) -> dict[str, Any] | None:
    conn = get_redis_connection()
    raw = conn.get(_key(session_id))
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)


def delete_retrieval_tree(session_id: str) -> None:
    conn = get_redis_connection()
    conn.delete(_key(session_id))
