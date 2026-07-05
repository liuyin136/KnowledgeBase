"""
app/workers/worker.py — RQ (Redis Queue) worker entrypoint.

Executed inside the `api-worker` Docker service via:
    python -m app.workers.worker

Responsibilities:
- Connect to the shared Redis instance used by ProgressTracker and RQ.
- Start an RQ Worker that listens on the configured queue (default: "default").
- Import `app.workers.tasks` so that `run_ingest_task` / `run_search_task`
  are discoverable (important if jobs are enqueued using their dotted path).
- Use the same structured JSON logging as the FastAPI backend.
- Pre-load nothing heavy; the PipelineOrchestrator + embedding model are
  initialized lazily inside the task on first execution (via singleton in tasks.py).
  This keeps worker startup fast and allows the same code path for
  BackgroundTasks (backend container) and RQ (api-worker container).

Environment variables (from docker-compose):
- REDIS_URL
- RQ_QUEUE_NAME
- LOG_LEVEL
- WORKER_CONCURRENCY (used at compose level to decide replica count)

This module follows the project's existing patterns:
- JSON structured logging via configure_logging()
- Minimal top-level code; logic in main()
- Clear separation: worker only handles queue consumption.
"""

from __future__ import annotations

import os
import sys

from redis import Redis
from rq import Worker, Queue

from app.core.logging import configure_logging
from app.workers import tasks  # Side-effect import: registers task functions for RQ
from app.workers.progress import ProgressTracker  # Available if worker needs direct access

import logging

logger = logging.getLogger("rag.workers.worker")


def main() -> None:
    """Bootstrap and run the RQ worker (blocking call)."""
    # 1. Structured logging (same format + silencing as uvicorn backend)
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    configure_logging(log_level)

    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    queue_name: str = os.getenv("RQ_QUEUE_NAME", "default")

    logger.info(
        "worker.starting",
        extra={
            "event": "worker.starting",
            "redis_url": redis_url,
            "queue_name": queue_name,
            "pid": os.getpid(),
            "python_version": sys.version.split()[0],
        },
    )

    try:
        # 2. Redis connection (decode_responses=True to match ProgressTracker)
        redis_conn = Redis.from_url(redis_url, decode_responses=True)
        redis_conn.ping()  # Fail fast if Redis unavailable

        # 3. Queue(s) to listen on — single queue for simplicity (GPU-bound work)
        queues = [Queue(queue_name, connection=redis_conn)]

        # 4. Create the worker instance
        worker = Worker(
            queues,
            connection=redis_conn,
            name=f"rag-api-worker-{os.getpid()}",
            # default_worker_ttl=420,  # optional: job lease time
            # exception_handler=...   # can be added later for alerting
        )

        logger.info(
            "worker.ready",
            extra={
                "event": "worker.ready",
                "queues": [q.name for q in queues],
                "worker_name": worker.name,
            },
        )

        # 5. Start consuming jobs (blocking until shutdown signal)
        # RQ will automatically deserialize and call the task function
        # with the arguments that were enqueued.
        worker.work(logging_level=log_level)

    except KeyboardInterrupt:
        logger.info("worker.shutdown", extra={"event": "worker.shutdown", "reason": "SIGINT"})
        sys.exit(0)
    except Exception as exc:
        logger.exception(
            "worker.fatal",
            extra={"event": "worker.fatal", "error": str(exc)},
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
