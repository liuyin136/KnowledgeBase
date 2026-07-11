"""RQ worker entrypoint for api-worker service."""
from __future__ import annotations

import os

import redis
from download_models2 import ensure_model
from rq import Queue, Worker

from app.workers import tasks  # noqa: F401 — register RQ task functions

ensure_model()


def main() -> None:
    from app.core.logging import configure_logging, get_logger
    from app.services.vault_db import init_vault_db
    from app.services.vault_sync import sync_vault

    configure_logging(os.environ.get("OTEL_SERVICE_NAME", "knowledgebase-worker"))
    logger = get_logger("rag.worker")

    try:
        init_vault_db()
        report = sync_vault()
        logger.info(
            "vault_startup_sync",
            files_scanned=report.files_scanned,
            drift_added=report.drift_added,
            drift_modified=report.drift_modified,
            drift_removed=report.drift_removed,
        )
    except Exception as exc:
        logger.warning("vault_startup_sync_failed", error=str(exc))

    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    queue_name = os.environ.get("RQ_QUEUE_NAME", "default")
    conn = redis.from_url(redis_url)
    queue = Queue(queue_name, connection=conn)
    worker = Worker([queue], connection=conn)
    worker.work()


if __name__ == "__main__":
    main()
