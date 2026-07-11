from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, Request

from app.middleware.otel import current_span_id
from app.models.file_schemas import (
    Category,
    CreateLogRequest,
    CreateLogResponse,
    FileContentResponse,
    FileListResponse,
    ReindexResponse,
    SaveContentRequest,
)
from app.services import file_store
from app.services.index_status import enrich_files_with_index_status
from app.core.exceptions import IngestBlockedError
from app.services.job_queue import enqueue_index_log, enqueue_ingest_document

router = APIRouter(prefix="/api/v1/files", tags=["files"])


@router.get("", response_model=FileListResponse)
def list_files(
    category: Category | None = Query(default=None),
    keyword: str | None = Query(default=None),
    date: str | None = Query(default=None, alias="date"),
) -> FileListResponse:
    files = file_store.list_files(category=category, keyword=keyword, filter_date=date)
    enriched = enrich_files_with_index_status(files)
    return FileListResponse(files=enriched, total=len(enriched))


@router.get("/content", response_model=FileContentResponse)
async def get_content(path: str = Query(...)) -> FileContentResponse:
    try:
        content, size = await file_store.read_content(path)
    except file_store.FileStoreError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return FileContentResponse(path=path, content=content, size=size)


@router.post("", response_model=CreateLogResponse)
async def create_log(body: CreateLogRequest, request: Request) -> CreateLogResponse:
    try:
        path, content = await file_store.create_log(body)
    except file_store.FileStoreError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    traceparent = request.headers.get("traceparent", "")
    try:
        job_id = enqueue_index_log(path)
        ingest_job_id = enqueue_ingest_document(path, traceparent=traceparent)
    except IngestBlockedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CreateLogResponse(path=path, content=content, job_id=job_id, ingest_job_id=ingest_job_id)


@router.put("/content", response_model=FileContentResponse)
async def save_content(body: SaveContentRequest, request: Request) -> FileContentResponse:
    try:
        await file_store.write_content(body.path, body.content)
        size = len(body.content.encode("utf-8"))
    except file_store.FileStoreError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    traceparent = request.headers.get("traceparent", "")
    try:
        ingest_job_id = enqueue_ingest_document(body.path, traceparent=traceparent)
    except IngestBlockedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileContentResponse(
        path=body.path,
        content=body.content,
        size=size,
        ingest_job_id=ingest_job_id,
    )


@router.post("/{path:path}/reindex", response_model=ReindexResponse)
def reindex_file(path: str, request: Request) -> ReindexResponse:
    traceparent = request.headers.get("traceparent", "")
    span_id = current_span_id() or uuid.uuid4().hex[:16]
    try:
        ingest_job_id = enqueue_ingest_document(path, traceparent=traceparent)
    except IngestBlockedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ReindexResponse(ingest_job_id=ingest_job_id, span_id=span_id)
