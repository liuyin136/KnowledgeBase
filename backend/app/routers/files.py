from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.models.file_schemas import (
    Category,
    CreateLogRequest,
    CreateLogResponse,
    FileContentResponse,
    FileListResponse,
    SaveContentRequest,
)
from app.services import file_store
from app.services.job_queue import enqueue_index_log

router = APIRouter(prefix="/api/v1/files", tags=["files"])


@router.get("", response_model=FileListResponse)
def list_files(
    category: Category | None = Query(default=None),
    keyword: str | None = Query(default=None),
    date: str | None = Query(default=None, alias="date"),
) -> FileListResponse:
    files = file_store.list_files(category=category, keyword=keyword, filter_date=date)
    return FileListResponse(files=files, total=len(files))


@router.get("/content", response_model=FileContentResponse)
async def get_content(path: str = Query(...)) -> FileContentResponse:
    try:
        content, size = await file_store.read_content(path)
    except file_store.FileStoreError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return FileContentResponse(path=path, content=content, size=size)


@router.post("", response_model=CreateLogResponse)
async def create_log(body: CreateLogRequest) -> CreateLogResponse:
    try:
        path, content = await file_store.create_log(body)
    except file_store.FileStoreError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    job_id = enqueue_index_log(path)
    return CreateLogResponse(path=path, content=content, job_id=job_id)


@router.put("/content", response_model=FileContentResponse)
async def save_content(body: SaveContentRequest) -> FileContentResponse:
    try:
        await file_store.write_content(body.path, body.content)
        size = len(body.content.encode("utf-8"))
    except file_store.FileStoreError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return FileContentResponse(path=body.path, content=body.content, size=size)
