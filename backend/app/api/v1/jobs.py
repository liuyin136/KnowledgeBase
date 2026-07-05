"""
api/v1/jobs.py — Generic job status endpoint.

  • GET /api/v1/jobs/{jobId} → JobStatusResponse

Reads from the ProgressTracker (Redis-backed). Works for both ingest and
search jobs — the `type` field in the response tells the client which.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import get_job_tracker
from app.schemas.ingest import JobStatusResponse
from app.workers.progress import ProgressTracker

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job(
    job_id: str,
    tracker: ProgressTracker = Depends(get_job_tracker),
) -> JobStatusResponse:
    return tracker.get_status(job_id)
