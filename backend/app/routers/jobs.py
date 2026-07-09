from __future__ import annotations

from fastapi import APIRouter, HTTPException
from rq.job import Job

from app.services.job_queue import get_redis_connection

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])

_STATUS_MAP = {
    "queued": "queued",
    "started": "started",
    "finished": "finished",
    "failed": "failed",
    "deferred": "queued",
    "scheduled": "queued",
    "stopped": "failed",
    "canceled": "failed",
}


@router.get("/{job_id}")
def get_job_status(job_id: str) -> dict:
    try:
        job = Job.fetch(job_id, connection=get_redis_connection())
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc

    raw_status = job.get_status()
    return {
        "job_id": job_id,
        "status": _STATUS_MAP.get(raw_status, raw_status),
        "result": job.result if job.is_finished else None,
        "error": str(job.exc_info) if job.is_failed else None,
    }
