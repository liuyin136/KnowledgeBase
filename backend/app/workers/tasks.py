"""
workers/tasks.py — Background ingest + search tasks.

Each task runs the PipelineOrchestrator and writes progress + final state to
the ProgressTracker (Redis-backed, in-memory fallback). Tasks are dispatched
by the API layer (api/v1/ingest.py, api/v1/search.py) via FastAPI's
BackgroundTasks — they run in-process. In production, the same task functions
can be invoked by the `api-worker` service (an RQ worker reading from the
same Redis queue) with no code changes.

Idempotency:
  • Each task owns exactly one job_id + one experiment_id.
  • Re-invoking a task with the same ids will create duplicate nodes —
    callers must generate fresh ids per logical run.
  • Failed runs persist Experiment.status='failed' so the UI shows the error.
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from typing import Optional

from app.core.constants import JobType
from app.core.exceptions import RAGBaseException
from app.core.logging import get_logger, log_pipeline_event
from app.db.neo4j_client import Neo4jClient
from app.schemas.experiment import IngestConfig
from app.schemas.ingest import IngestProgressEvent
from app.schemas.search import SearchConfig
from app.services.embedding import EmbeddingModule
from app.services.orchestrator import PipelineOrchestrator
from app.services.retrieval import RetrievalModule
from app.workers.progress import ProgressTracker, get_progress_tracker

logger = get_logger("rag.workers.tasks")


# ─── Orchestrator singleton (shared across tasks) ─────────────────────────────

_orchestrator: Optional[PipelineOrchestrator] = None
_orchestrator_lock = threading.Lock()


def get_orchestrator(
    neo4j: Neo4jClient,
    embedder: EmbeddingModule,
) -> PipelineOrchestrator:
    """Return a shared orchestrator (one per process)."""
    global _orchestrator
    if _orchestrator is None:
        with _orchestrator_lock:
            if _orchestrator is None:
                retrieval = RetrievalModule(neo4j)
                _orchestrator = PipelineOrchestrator(neo4j, embedder, retrieval)
    return _orchestrator


# ─── Ingest task ──────────────────────────────────────────────────────────────


def run_ingest_task(
    *,
    job_id: str,
    experiment_id: str,
    document_id: str,
    config: IngestConfig,
    description: Optional[str],
    text: str,
    neo4j: Neo4jClient,
    embedder: EmbeddingModule,
    tracker: Optional[ProgressTracker] = None,
) -> None:
    """Synchronous entry point — runs the async ingest pipeline in a new event loop.

    Designed to be called from FastAPI BackgroundTasks (sync callable).
    """
    tracker = tracker or get_progress_tracker()
    tracker.mark_running(job_id, total=0)
    log_pipeline_event(
        logger,
        "task.ingest.start",
        f"Ingest task started: job={job_id} experiment={experiment_id}",
        job_id=job_id,
        experiment_id=experiment_id,
        document_id=document_id,
        config=config.model_dump(),
    )

    def progress_cb(event: IngestProgressEvent) -> None:
        tracker.append_event(job_id, event)

    try:
        orch = get_orchestrator(neo4j, embedder)
        if config.embeddingApproach.value == "LongText":
            coro = orch.ingest_long_text(
                experiment_id=experiment_id,
                source_file=document_id,
                text=text,
                description=description or f"LongText ingest of {document_id}",
                progress=progress_cb,
            )
        else:  # ChildChunk
            coro = orch.ingest_child_chunk(
                experiment_id=experiment_id,
                source_file=document_id,
                text=text,
                chunk_method=config.chunkMethod.value,
                description=description or f"ChildChunk ingest of {document_id} ({config.chunkMethod.value})",
                progress=progress_cb,
            )
        # Run the async coroutine in a fresh event loop.
        asyncio.run(coro)
        tracker.mark_completed(job_id)
        log_pipeline_event(
            logger,
            "task.ingest.done",
            f"Ingest task completed: job={job_id}",
            job_id=job_id,
            experiment_id=experiment_id,
        )
    except RAGBaseException as exc:
        tracker.mark_failed(job_id, error_code=exc.code, error_message=exc.message)
        logger.error(
            "task.ingest.failed",
            extra={
                "event": "task.ingest.failed",
                "job_id": job_id,
                "experiment_id": experiment_id,
                "error_code": exc.code,
                "error": exc.message,
            },
        )
    except Exception as exc:
        tracker.mark_failed(job_id, error_code="INTERNAL_ERROR", error_message=str(exc))
        logger.exception("task.ingest.unexpected_error", extra={"job_id": job_id})


# ─── Search task ──────────────────────────────────────────────────────────────


def run_search_task(
    *,
    job_id: str,
    search_id: str,
    experiment_id: str,
    raw_query: str,
    config: SearchConfig,
    neo4j: Neo4jClient,
    embedder: EmbeddingModule,
    tracker: Optional[ProgressTracker] = None,
) -> None:
    """Synchronous entry point — runs the async search pipeline in a new event loop."""
    tracker = tracker or get_progress_tracker()
    tracker.mark_running(job_id, total=1)
    log_pipeline_event(
        logger,
        "task.search.start",
        f"Search task started: job={job_id} search={search_id}",
        job_id=job_id,
        search_id=search_id,
        experiment_id=experiment_id,
        config=config.model_dump(),
    )

    def progress_cb(event: IngestProgressEvent) -> None:
        tracker.append_event(job_id, event)

    try:
        orch = get_orchestrator(neo4j, embedder)
        response = asyncio.run(
            orch.run_search(
                search_id=search_id,
                experiment_id=experiment_id,
                raw_query=raw_query,
                config=config,
                progress=progress_cb,
            )
        )
        tracker.mark_completed(job_id, result=response)
        log_pipeline_event(
            logger,
            "task.search.done",
            f"Search task completed: job={job_id} results={len(response.results)}",
            job_id=job_id,
            search_id=search_id,
            result_count=len(response.results),
        )
    except RAGBaseException as exc:
        tracker.mark_failed(job_id, error_code=exc.code, error_message=exc.message)
        logger.error(
            "task.search.failed",
            extra={
                "event": "task.search.failed",
                "job_id": job_id,
                "search_id": search_id,
                "error_code": exc.code,
                "error": exc.message,
            },
        )
    except Exception as exc:
        tracker.mark_failed(job_id, error_code="INTERNAL_ERROR", error_message=str(exc))
        logger.exception("task.search.unexpected_error", extra={"job_id": job_id})
