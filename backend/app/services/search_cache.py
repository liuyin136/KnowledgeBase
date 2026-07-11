from __future__ import annotations

import hashlib
import json
from typing import Any

import redis

from app.core.config import get_settings
from app.core.constants import SEARCH_CACHE_VERSION


def _redis() -> redis.Redis:
    return redis.from_url(get_settings().redis_url)


def cache_key(
    *,
    query: str,
    w1: float,
    w2: float,
    recall_k: int,
    rerank_k: int,
    coarse_dim: int,
    use_minmax_fallback: bool,
    folder_ids: list[str] | None = None,
    created_after: str | None = None,
    created_before: str | None = None,
    indexed_only: bool = True,
) -> str:
    sorted_ids = ",".join(sorted(folder_ids or []))
    raw = (
        f"{SEARCH_CACHE_VERSION}|{query}|{w1}|{w2}|{recall_k}|{rerank_k}|{coarse_dim}|{use_minmax_fallback}"
        f"|{sorted_ids}|{created_after or ''}|{created_before or ''}|{indexed_only}"
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"search:{digest}"


def get_cached(key: str) -> dict[str, Any] | None:
    raw = _redis().get(key)
    if not raw:
        return None
    return json.loads(raw)


def set_cached(key: str, payload: dict[str, Any]) -> None:
    ttl = get_settings().search_cache_ttl
    _redis().setex(key, ttl, json.dumps(payload))
