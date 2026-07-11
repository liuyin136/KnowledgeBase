from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.models.search_schemas import SearchRequest, SearchResponse, WorkflowPhase
from app.services import search_cache
from app.services.job_queue import enqueue_hybrid_search
from app.middleware.otel import current_span_id
from app.services.vault_scope import AllowlistTooLargeError, resolve_search_allowlist

router = APIRouter(prefix="/api/v1/search", tags=["search"])


def _scope_active(body: SearchRequest) -> bool:
    if body.folder_ids is not None:
        return True
    if body.created_after is not None or body.created_before is not None:
        return True
    if body.indexed_only is False:
        return True
    return False


def _scope_meta(body: SearchRequest) -> dict[str, Any]:
    return {
        "folder_ids": body.folder_ids,
        "created_after": body.created_after.isoformat() if body.created_after else None,
        "created_before": body.created_before.isoformat() if body.created_before else None,
        "indexed_only": body.indexed_only,
    }


def _cache_scope_kwargs(body: SearchRequest) -> dict[str, Any]:
    if not _scope_active(body):
        return {}
    return {
        "folder_ids": body.folder_ids,
        "created_after": body.created_after.isoformat() if body.created_after else None,
        "created_before": body.created_before.isoformat() if body.created_before else None,
        "indexed_only": body.indexed_only,
    }


@router.post("", response_model=SearchResponse)
def search(body: SearchRequest, request: Request) -> SearchResponse:
    span_id = current_span_id() or uuid.uuid4().hex[:16]
    traceparent = request.headers.get("traceparent", "")

    allowed_paths: list[str] | None = None
    scope_meta: dict[str, Any] | None = None

    if _scope_active(body):
        scope_meta = _scope_meta(body)
        try:
            allowed_paths = resolve_search_allowlist(
                body.folder_ids,
                body.created_after,
                body.created_before,
                body.indexed_only,
            )
        except AllowlistTooLargeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        if body.indexed_only and len(allowed_paths) == 0:
            workflow_log = [
                WorkflowPhase(
                    phase="vault_scope",
                    status="done",
                    latency_ms=0,
                    hit_count=0,
                )
            ]
            return SearchResponse(
                cached=False,
                span_id=span_id,
                hits=[],
                fusion_meta={
                    "pool_size": 0,
                    "w1": body.w1,
                    "w2": body.w2,
                    "recall_k": body.recall_k,
                    "rerank_k": body.rerank_k,
                    "coarse_dim": body.coarse_dim,
                    "rescore_dim": 1024,
                    "latency_ms": 0,
                    "allowlist_size": 0,
                    **scope_meta,
                },
                workflow_log=workflow_log,
            )

    key = search_cache.cache_key(
        query=body.query,
        w1=body.w1,
        w2=body.w2,
        recall_k=body.recall_k,
        rerank_k=body.rerank_k,
        coarse_dim=body.coarse_dim,
        use_minmax_fallback=body.use_minmax_fallback,
        **_cache_scope_kwargs(body),
    )
    cached = search_cache.get_cached(key)
    if cached:
        return SearchResponse(
            cached=True,
            span_id=cached.get("span_id", span_id),
            hits=cached.get("hits"),
            fusion_meta=cached.get("fusion_meta"),
            workflow_log=cached.get("workflow_log"),
        )

    job_id = enqueue_hybrid_search(
        query=body.query,
        w1=body.w1,
        w2=body.w2,
        recall_k=body.recall_k,
        rerank_k=body.rerank_k,
        coarse_dim=body.coarse_dim,
        use_minmax_fallback=body.use_minmax_fallback,
        traceparent=traceparent,
        cache_key=key,
        span_id=span_id,
        allowed_paths=allowed_paths,
        scope_meta=scope_meta,
    )
    return SearchResponse(job_id=job_id, span_id=span_id, cached=False)
