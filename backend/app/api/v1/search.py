"""
api/v1/search.py — Search endpoints.

  • POST  /api/v1/search              → 202 {jobId, searchId, status}
  • GET   /api/v1/searches/history    → paginated list of past search experiments

The POST endpoint:
  1. Generates experiment_id (run tag, no :Experiment node).
  2. Creates a job in the ProgressTracker.
  3. Dispatches the background search task.
  4. Returns 202 immediately with {jobId, searchId, status:"queued"}.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query

from app.api.dependencies import get_db, get_embedding_module, get_job_tracker
from app.core.constants import JobType
from app.db.neo4j_client import Neo4jClient
from app.schemas.common import Paginated
# ExperimentResponse no longer used; search history stubbed as no :Experiment node
from app.schemas.ingest import JobStatusResponse
from app.schemas.search import StartSearchRequest, StartSearchResponse
from app.services.embedding import EmbeddingModule
from app.workers.progress import ProgressTracker
from app.workers.tasks import run_search_task

router = APIRouter(tags=["search"])


@router.post("/search", response_model=StartSearchResponse, status_code=202)
def start_search(
    body: StartSearchRequest,
    background_tasks: BackgroundTasks,
    db: Neo4jClient = Depends(get_db),
    embedder: EmbeddingModule = Depends(get_embedding_module),
    tracker: ProgressTracker = Depends(get_job_tracker),
) -> StartSearchResponse:
    experiment_id = str(uuid.uuid4())
    search_id = str(uuid.uuid4())
    job_id = tracker.create_job(
        job_type=JobType.SEARCH,
        experiment_id=experiment_id,
        search_id=search_id,
    )
    background_tasks.add_task(
        run_search_task,
        job_id=job_id,
        search_id=search_id,
        experiment_id=experiment_id,
        raw_query=body.rawQuery,
        config=body.config,
        neo4j=db,
        embedder=embedder,
        tracker=tracker,
    )
    return StartSearchResponse(
        jobId=job_id,
        searchId=search_id,
        status="queued",
    )


@router.get("/searches/history", response_model=Paginated[dict])
def search_history(
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
    experimentId: Optional[str] = Query(default=None),
    db: Neo4jClient = Depends(get_db),
) -> Paginated[dict]:
    """Search history stub: :Experiment node removed per redesign.
    Returns empty for now. Use document/source_file based history in Documents view.
    """
    # All experiment node related deleted. No more list_experiments or get_experiment.
    return Paginated[dict](
        items=[],
        total=0,
        page=page,
        pageSize=pageSize,
        hasMore=False,
    )
