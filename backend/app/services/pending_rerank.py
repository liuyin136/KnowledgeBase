"""Redis-backed pending rerank state between fusion and user-confirmed rerank."""
from __future__ import annotations

import json
from typing import Any

from app.core.config import get_settings
from app.services.job_queue import get_redis_connection

_KEY_PREFIX = "search:pending_rerank:"


def _key(job_id: str) -> str:
    return f"{_KEY_PREFIX}{job_id}"


def save_pending(job_id: str, payload: dict[str, Any]) -> None:
    ttl = get_settings().pending_rerank_ttl_sec
    conn = get_redis_connection()
    conn.setex(_key(job_id), ttl, json.dumps(payload, ensure_ascii=False, default=str))


def load_pending(job_id: str) -> dict[str, Any] | None:
    conn = get_redis_connection()
    raw = conn.get(_key(job_id))
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)


def delete_pending(job_id: str) -> None:
    conn = get_redis_connection()
    conn.delete(_key(job_id))
