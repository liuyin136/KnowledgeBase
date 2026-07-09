"""RQ worker entrypoint for api-worker service."""
from __future__ import annotations

import os

import redis
from download_models2 import ensure_model
from rq import Queue, Worker

from app.workers import tasks  # noqa: F401 — register RQ task functions

ensure_model()


def main() -> None:
    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    queue_name = os.environ.get("RQ_QUEUE_NAME", "default")
    conn = redis.from_url(redis_url)
    queue = Queue(queue_name, connection=conn)
    worker = Worker([queue], connection=conn)
    worker.work()


if __name__ == "__main__":
    main()
