from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any

import redis

from app.core.constants import METRICS_LIST_KEY, METRICS_LIST_MAX


def _redis() -> redis.Redis:
    url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    return redis.from_url(url)


def push_metrics(record: dict[str, Any]) -> None:
    payload = {
        **record,
        "timestamp": record.get("timestamp") or datetime.now(timezone.utc).isoformat(),
    }
    redis_conn = _redis()
    redis_conn.lpush(METRICS_LIST_KEY, json.dumps(payload))
    redis_conn.ltrim(METRICS_LIST_KEY, 0, METRICS_LIST_MAX - 1)


def timed_metrics(stage: str):
    """Decorator factory: push one metrics record after function completes."""

    def decorator(fn):
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            error_code = None
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                error_code = type(exc).__name__
                raise
            finally:
                latency_ms = int((time.perf_counter() - start) * 1000)
                push_metrics(
                    {
                        "stage": stage,
                        "latency_ms": latency_ms,
                        "error_code": error_code,
                    }
                )

        wrapper.__name__ = fn.__name__
        return wrapper

    return decorator
