from __future__ import annotations

from fastapi import APIRouter, HTTPException
from rq.job import Job

from app.core.config import get_settings
from app.models.search_schemas import (
    FusionMeta,
    IngestPhase,
    IngestProgress,
    RerankConfirmRequest,
    RerankConfirmResponse,
    RerankPreviewMeta,
    SearchHit,
    SearchProgress,
    WorkflowPhase,
)
from app.services import ingest_progress, pending_rerank, retrieval_memory, search_progress
from app.services.job_queue import enqueue_hybrid_rerank, get_redis_connection

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


def _result_status(result: dict | None) -> str | None:
    if not isinstance(result, dict):
        return None
    status = result.get("status")
    if status in ("awaiting_rerank", "finished", "skipped_rerank"):
        return status
    if status is None and "hits" in result:
        return "finished"
    return status


def _rerank_preview_from_result(result: dict) -> RerankPreviewMeta | None:
    if result.get("rerank_token_count") is None:
        return None
    fusion_meta = result.get("fusion_meta") or {}
    return RerankPreviewMeta(
        rerank_token_count=int(result["rerank_token_count"]),
        rerank_ctx_limit=int(result.get("rerank_ctx_limit") or get_settings().rerank_n_ctx),
        rerank_doc_count=int(result.get("rerank_doc_count") or 0),
        rerank_k=int(fusion_meta.get("rerank_k") or 10),
    )


@router.get("/{job_id}")
def get_job_status(job_id: str) -> dict:
    try:
        job = Job.fetch(job_id, connection=get_redis_connection())
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc

    raw_status = job.get_status()
    mapped = _STATUS_MAP.get(raw_status, raw_status)
    result = job.result if job.is_finished else None
    result_status = _result_status(result)

    status = mapped
    if mapped == "finished" and result_status == "awaiting_rerank":
        status = "awaiting_rerank"

    payload: dict = {
        "job_id": job_id,
        "status": status,
        "result": result,
        "error": str(job.exc_info) if job.is_failed else None,
    }
    if mapped in ("queued", "started"):
        raw_progress = search_progress.load_progress(job_id)
        if raw_progress:
            workflow_log = [
                WorkflowPhase(**p) for p in (raw_progress.get("workflow_log") or [])
            ]
            payload["progress"] = SearchProgress(
                workflow_log=workflow_log,
                active_phase=raw_progress.get("active_phase"),
                span_id=raw_progress.get("span_id"),
            ).model_dump()
        else:
            ingest_raw = ingest_progress.load_progress(job_id)
            if ingest_raw:
                ingest_log = [
                    IngestPhase(**p) for p in (ingest_raw.get("workflow_log") or [])
                ]
                payload["ingest_progress"] = IngestProgress(
                    workflow_log=ingest_log,
                    active_phase=ingest_raw.get("active_phase"),
                    relative_path=ingest_raw.get("relative_path"),
                ).model_dump()
    if isinstance(result, dict) and result_status == "awaiting_rerank":
        preview = _rerank_preview_from_result(result)
        if preview:
            payload["rerank_preview"] = preview.model_dump()
    return payload


@router.post("/{job_id}/rerank", response_model=RerankConfirmResponse)
def confirm_rerank(job_id: str, body: RerankConfirmRequest) -> RerankConfirmResponse:
    try:
        job = Job.fetch(job_id, connection=get_redis_connection())
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc

    if not job.is_finished:
        raise HTTPException(status_code=409, detail="Fusion job not finished yet")

    result = job.result
    if not isinstance(result, dict):
        raise HTTPException(status_code=409, detail="Invalid fusion job result")

    if _result_status(result) != "awaiting_rerank":
        raise HTTPException(status_code=409, detail="Job is not awaiting rerank confirmation")

    pending = pending_rerank.load_pending(job_id)
    if pending is None:
        raise HTTPException(status_code=410, detail="Rerank session expired; run search again")

    preview = _rerank_preview_from_result(result)
    if not body.confirm:
        pending_rerank.delete_pending(job_id)
        tree = pending.get("retrieval_tree") or {}
        if tree:
            retrieval_memory.save_retrieval_tree(
                job_id,
                parent_ids=tree.get("parent_ids") or [],
                child_ids=tree.get("child_ids") or [],
                grandchild_ids=tree.get("grandchild_ids") or [],
                span_id=pending.get("span_id") or result.get("span_id"),
                query=pending.get("query"),
            )
        hits = [SearchHit(**h) for h in pending.get("hits_fusion") or result.get("hits") or []]
        workflow_log = [
            WorkflowPhase(**p) for p in (pending.get("workflow_log") or result.get("workflow_log") or [])
        ]
        fusion_meta = FusionMeta(**(pending.get("fusion_meta") or result.get("fusion_meta") or {}))
        return RerankConfirmResponse(
            status="skipped_rerank",
            hits=hits,
            fusion_meta=fusion_meta,
            workflow_log=workflow_log,
            span_id=pending.get("span_id") or result.get("span_id"),
            rerank_preview=preview,
        )

    rerank_job_id = enqueue_hybrid_rerank(job_id)
    return RerankConfirmResponse(
        status="rerank_started",
        rerank_job_id=rerank_job_id,
        rerank_preview=preview,
        span_id=pending.get("span_id") or result.get("span_id"),
    )
