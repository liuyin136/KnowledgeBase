"""
api/v1/search.py — Search endpoints.

  • POST  /api/v1/search              → 202 {jobId, searchId, status}
  • GET   /api/v1/searches/history    → paginated list of past search experiments

The POST endpoint:
  1. Creates a fresh :Experiment record (kind=search, status=pending).
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
from app.schemas.experiment import ExperimentResponse
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


@router.get("/searches/history", response_model=Paginated[ExperimentResponse])
def search_history(
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
    experimentId: Optional[str] = Query(default=None),
    db: Neo4jClient = Depends(get_db),
) -> Paginated[ExperimentResponse]:
    """Return paginated search-kind experiments.

    If `experimentId` is provided, filter to that single experiment (the
    frontend uses this for the search history view filtered by active experiment).
    """
    # Reuse the experiments list with kind=search filter
    from app.api.v1.experiments import _exp_to_response

    if experimentId:
        # Single experiment lookup
        e = db.get_experiment(experimentId)
        if not e:
            return Paginated[ExperimentResponse](
                items=[], total=0, page=page, pageSize=pageSize, hasMore=False
            )
        items = [_exp_to_response(e)]
        return Paginated[ExperimentResponse](
            items=items, total=1, page=1, pageSize=pageSize, hasMore=False
        )

    items_raw, total = db.list_experiments(kind="search", page=page, page_size=pageSize)
    items = [_exp_to_response(i) for i in items_raw]
    return Paginated[ExperimentResponse](
        items=items,
        total=total,
        page=page,
        pageSize=pageSize,
        hasMore=(page * pageSize) < total,
    )
