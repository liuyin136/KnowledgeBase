"""Manual GraphRAG memory extract API."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request, status

from app.middleware.otel import current_span_id
from app.models.memory_schemas import (
    MemoryBundleResponse,
    MemoryExtractRequest,
    MemoryExtractResponse,
)
from app.services.job_queue import enqueue_extract_memory_graph
from app.services.neo4j_client import get_neo4j_client

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


@router.post("/extract", status_code=status.HTTP_202_ACCEPTED, response_model=MemoryExtractResponse)
def extract_memory(body: MemoryExtractRequest, request: Request) -> MemoryExtractResponse:
    trace_id = current_span_id() or uuid.uuid4().hex[:16]
    traceparent = request.headers.get("traceparent", "")
    try:
        job_id = enqueue_extract_memory_graph(
            query_text=body.query_text,
            grandchild_ids=body.grandchild_ids,
            user_query_id=body.user_query_id,
            session_id=body.session_id,
            traceparent=traceparent,
            span_id=trace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return MemoryExtractResponse(job_id=job_id, trace_id=trace_id)


@router.get("/{memory_key}", response_model=MemoryBundleResponse)
def get_memory(memory_key: str) -> MemoryBundleResponse:
    bundle = get_neo4j_client().get_memory_bundle(memory_key)
    if not bundle:
        raise HTTPException(status_code=404, detail="Memory not found")
    memory = bundle.get("memory") or {}
    return MemoryBundleResponse(
        memory_key=memory_key,
        memory_id=memory.get("id"),
        content=memory.get("content"),
        version=int(memory.get("version") or 0),
        entity_count=int(bundle.get("entity_count") or 0),
        claim_count=int(bundle.get("claim_count") or 0),
        community_count=int(bundle.get("community_count") or 0),
        grandchild_count=int(bundle.get("grandchild_count") or 0),
    )
