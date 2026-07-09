from __future__ import annotations

import redis
from rq import Queue

from app.core.config import get_settings
from app.workers.tasks import index_log_file

_redis: redis.Redis | None = None


def get_redis_connection() -> redis.Redis:
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = redis.from_url(settings.redis_url)
    return _redis


def get_queue() -> Queue:
    settings = get_settings()
    queue_name = settings.rq_queue_name
    return Queue(queue_name, connection=get_redis_connection())


def enqueue_index_log(relative_path: str) -> str:
    job = get_queue().enqueue(index_log_file, relative_path)
    return job.id
