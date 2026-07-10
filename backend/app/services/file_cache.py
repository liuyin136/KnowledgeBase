from __future__ import annotations

import redis

from app.core.config import get_settings

_redis: redis.Redis | None = None


def _client() -> redis.Redis:
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def cache_key(relative_path: str) -> str:
    return f"file:{relative_path}"


def get_cached(relative_path: str) -> str | None:
    try:
        return _client().get(cache_key(relative_path))
    except redis.RedisError:
        return None


def set_cached(relative_path: str, content: str) -> None:
    settings = get_settings()
    try:
        _client().setex(cache_key(relative_path), settings.file_cache_ttl, content)
    except redis.RedisError:
        pass


def invalidate(relative_path: str) -> None:
    try:
        _client().delete(cache_key(relative_path))
    except redis.RedisError:
        pass
