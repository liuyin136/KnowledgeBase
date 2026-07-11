"""Redis-backed live ingest workflow progress for in-flight jobs."""
from __future__ import annotations

import json
from typing import Any

from app.core.config import get_settings
from app.services.job_queue import get_redis_connection

_KEY_PREFIX = "ingest:progress:"


def _key(job_id: str) -> str:
    return f"{_KEY_PREFIX}{job_id}"


def _ttl_sec() -> int:
    return get_settings().ingest_progress_ttl_sec


def _save(job_id: str, payload: dict[str, Any]) -> None:
    conn = get_redis_connection()
    conn.setex(_key(job_id), _ttl_sec(), json.dumps(payload, ensure_ascii=False, default=str))


def init_progress(
    job_id: str,
    *,
    active_phase: str,
    relative_path: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "workflow_log": [],
        "active_phase": active_phase,
    }
    if relative_path:
        payload["relative_path"] = relative_path
    _save(job_id, payload)


def update_progress(
    job_id: str,
    workflow_log: list[dict[str, Any]],
    active_phase: str | None,
    *,
    relative_path: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "workflow_log": workflow_log,
        "active_phase": active_phase,
    }
    if relative_path:
        payload["relative_path"] = relative_path
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
