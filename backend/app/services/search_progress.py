"""Redis-backed live search workflow progress for in-flight jobs."""
from __future__ import annotations

import json
from typing import Any

from app.core.config import get_settings
from app.services.job_queue import get_redis_connection

_KEY_PREFIX = "search:progress:"


def _key(job_id: str) -> str:
    return f"{_KEY_PREFIX}{job_id}"


def _ttl_sec() -> int:
    return get_settings().pending_rerank_ttl_sec


def _save(job_id: str, payload: dict[str, Any]) -> None:
    conn = get_redis_connection()
    conn.setex(_key(job_id), _ttl_sec(), json.dumps(payload, ensure_ascii=False, default=str))


def init_progress(
    job_id: str,
    *,
    active_phase: str,
    span_id: str | None = None,
    workflow_log: list[dict[str, Any]] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "workflow_log": list(workflow_log or []),
        "active_phase": active_phase,
    }
    if span_id:
        payload["span_id"] = span_id
    _save(job_id, payload)


def update_progress(
    job_id: str,
    workflow_log: list[dict[str, Any]],
    active_phase: str | None,
    *,
    span_id: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "workflow_log": workflow_log,
        "active_phase": active_phase,
    }
    if span_id:
        payload["span_id"] = span_id
    _save(job_id, payload)


def load_progress(job_id: str) -> dict[str, Any] | None:
    conn = get_redis_connection()
    raw = conn.get(_key(job_id))
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)


def clear_progress(job_id: str) -> None:
    conn = get_redis_connection()
    conn.delete(_key(job_id))
