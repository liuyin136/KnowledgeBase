"""
api/v1/ingest.py — Ingest endpoints.

  • POST  /api/v1/ingest                    → 202 {jobId, experimentId, status}
  • GET   /api/v1/ingest/{jobId}/status     → JobStatusResponse

The POST endpoint:
  1. Looks up the document text from Neo4j (Knowledge node stored at upload).
  2. Generates experiment_id (run tag, no :Experiment node).
  3. Creates a job in the ProgressTracker (Redis).
  4. Dispatches the background ingest task (FastAPI BackgroundTasks).
  5. Returns 202 immediately with {jobId, experimentId, status:"queued"}.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends

from app.api.dependencies import get_db, get_embedding_module, get_job_tracker
from app.core.constants import JobType
from app.core.exceptions import NotFoundError, ValidationError
from app.db.neo4j_client import Neo4jClient
from app.schemas.ingest import JobStatusResponse, StartIngestRequest, StartIngestResponse
from app.services.embedding import EmbeddingModule
from app.workers.progress import ProgressTracker
from app.workers.tasks import run_ingest_task

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("", response_model=StartIngestResponse, status_code=202)
def start_ingest(
    body: StartIngestRequest,
    background_tasks: BackgroundTasks,
    db: Neo4jClient = Depends(get_db),
    embedder: EmbeddingModule = Depends(get_embedding_module),
    tracker: ProgressTracker = Depends(get_job_tracker),
) -> StartIngestResponse:
    """Start an ingest job. Returns 202 with the job + experiment ids immediately."""
    # 1. Recover document text from Neo4j
    text = db.get_document_text(body.documentId)
    if not text:
        raise NotFoundError(
            f"Document {body.documentId} not found (no :Knowledge nodes with that source_file)",
            details={"documentId": body.documentId},
        )

    # 2. Create a fresh experiment record (status=pending — the task will set running)
    experiment_id = str(uuid.uuid4())
    job_id = tracker.create_job(
        job_type=JobType.INGEST,
        experiment_id=experiment_id,
    )

    # 3. Dispatch the background task
    background_tasks.add_task(
        run_ingest_task,
        job_id=job_id,
        experiment_id=experiment_id,
        document_id=body.documentId,
        config=body.config,
        description=body.experimentDescription,
        text=text,
        neo4j=db,
        embedder=embedder,
        tracker=tracker,
    )

    return StartIngestResponse(
        jobId=job_id,
        experimentId=experiment_id,
        status="queued",
    )


@router.get("/{job_id}/status", response_model=JobStatusResponse)
def get_ingest_status(
    job_id: str,
    tracker: ProgressTracker = Depends(get_job_tracker),
) -> JobStatusResponse:
    """Poll job status. Raises 404 JOB_NOT_FOUND if the job id is unknown."""
    return tracker.get_status(job_id)
