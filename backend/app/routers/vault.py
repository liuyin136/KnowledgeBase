"""RAG Content Vault REST API."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile

from app.models.vault_schemas import (
    BatchDeleteRequest,
    BatchDeleteItem,
    BatchDeleteResult,
    BatchStatusResponse,
    BatchUploadFileResult,
    BatchUploadResponse,
    CreateFileRequest,
    CreateFolderRequest,
    FolderListResponse,
    FolderRenamePreview,
    PaginatedFilesResponse,
    RenameFolderRequest,
    ReindexResponse,
    SaveContentRequest,
    SyncReport,
    UploadResponse,
    VaultFile,
    VaultFolder,
    PAGE_SIZES,
)
from app.services import vault_db, vault_store
from app.services.job_queue import enqueue_vault_ingest
from app.services.vault_store import VaultStoreError
from app.services.vault_sync import sync_vault

router = APIRouter(prefix="/api/v1/rag/vault", tags=["vault"])

SYNC_STALE_SECONDS = 300


def _raise_store(exc: VaultStoreError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


def _maybe_stale_sync() -> None:
    state = vault_db.get_sync_state()
    last = state.get("last_sync_at")
    if not last:
        sync_vault()
        return
    try:
        ts = datetime.fromisoformat(last.replace("Z", "+00:00"))
    except ValueError:
        sync_vault()
        return
    age = (datetime.now(timezone.utc) - ts).total_seconds()
    if age > SYNC_STALE_SECONDS:
        sync_vault()


@router.get("/folders", response_model=FolderListResponse)
def get_folders() -> FolderListResponse:
    return FolderListResponse(folders=vault_store.list_folders())


@router.post("/folders", response_model=VaultFolder, status_code=201)
def post_folder(body: CreateFolderRequest) -> VaultFolder:
    try:
        return vault_store.create_folder(body.name)
    except VaultStoreError as exc:
        _raise_store(exc)
        raise  # pragma: no cover


@router.get("/folders/{folder_id}/rename-preview", response_model=FolderRenamePreview)
def get_folder_rename_preview(
    folder_id: str, name: str = Query(..., min_length=1, max_length=120)
) -> FolderRenamePreview:
    try:
        return vault_store.preview_folder_rename(folder_id, name)
    except VaultStoreError as exc:
        _raise_store(exc)
        raise  # pragma: no cover


@router.patch("/folders/{folder_id}", response_model=VaultFolder)
def patch_folder(folder_id: str, body: RenameFolderRequest) -> VaultFolder:
    try:
        return vault_store.rename_folder(folder_id, body.name)
    except VaultStoreError as exc:
        _raise_store(exc)
        raise  # pragma: no cover


@router.delete("/folders/{folder_id}", status_code=204)
def remove_folder(folder_id: str) -> None:
    try:
        vault_store.delete_folder(folder_id)
    except VaultStoreError as exc:
        _raise_store(exc)


@router.get("/files", response_model=PaginatedFilesResponse)
def get_files(
    folder_id: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    index_status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10),
) -> PaginatedFilesResponse:
    if page_size not in PAGE_SIZES:
        raise HTTPException(
            status_code=422,
            detail=f"page_size must be one of {sorted(PAGE_SIZES)}",
        )
    _maybe_stale_sync()
    return vault_store.list_files(
        folder_id=folder_id,
        keyword=keyword,
        index_status=index_status,
        page=page,
        page_size=page_size,
    )


@router.post("/files", response_model=UploadResponse, status_code=201)
def post_file(
    body: CreateFileRequest,
    request: Request,
    on_conflict: str = Query(default="replace"),
) -> UploadResponse:
    if on_conflict not in ("replace", "fail"):
        raise HTTPException(status_code=422, detail="on_conflict must be replace or fail")
    try:
        result = vault_store.create_text_file(
            folder_id=body.folder_id,
            filename=body.filename,
            content=body.content,
            source="created",
            on_conflict=on_conflict,  # type: ignore[arg-type]
        )
    except VaultStoreError as exc:
        _raise_store(exc)
        raise  # pragma: no cover
    traceparent = request.headers.get("traceparent", "")
    job_id = enqueue_vault_ingest(result.file.id, traceparent=traceparent)
    refreshed = vault_store.get_file(result.file.id)
    return UploadResponse(file=refreshed, ingest_job_id=job_id, replaced=result.replaced)


@router.post("/files/upload", response_model=UploadResponse, status_code=201)
async def upload_file(
    request: Request,
    folder_id: str = Form(...),
    file: UploadFile = File(...),
    on_conflict: str = Query(default="replace"),
) -> UploadResponse:
    if on_conflict not in ("replace", "fail"):
        raise HTTPException(status_code=422, detail="on_conflict must be replace or fail")
    data = await file.read()
    filename = file.filename or "upload.md"
    try:
        result = vault_store.upload_file(
            folder_id=folder_id,
            filename=filename,
            data=data,
            on_conflict=on_conflict,  # type: ignore[arg-type]
        )
    except VaultStoreError as exc:
        _raise_store(exc)
        raise  # pragma: no cover
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="File must be UTF-8 text") from exc
    traceparent = request.headers.get("traceparent", "")
    job_id = enqueue_vault_ingest(result.file.id, traceparent=traceparent)
    return UploadResponse(
        file=vault_store.get_file(result.file.id),
        ingest_job_id=job_id,
        replaced=result.replaced,
    )


@router.post("/files/batch-upload", response_model=BatchUploadResponse, status_code=201)
async def batch_upload(
    request: Request,
    folder_id: str = Form(...),
    files: list[UploadFile] = File(...),
    on_conflict: str = Query(default="replace"),
) -> BatchUploadResponse:
    import uuid

    if on_conflict not in ("replace", "fail"):
        raise HTTPException(status_code=422, detail="on_conflict must be replace or fail")
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    batch_id = str(uuid.uuid4())
    vault_db.insert_batch(batch_id=batch_id, total_files=len(files))
    results: list[BatchUploadFileResult] = []
    traceparent = request.headers.get("traceparent", "")

    for upload in files:
        filename = upload.filename or "upload.md"
        data = await upload.read()
        try:
            result = vault_store.upload_file(
                folder_id=folder_id,
                filename=filename,
                data=data,
                on_conflict=on_conflict,  # type: ignore[arg-type]
            )
            job_id = enqueue_vault_ingest(result.file.id, traceparent=traceparent)
            vault_db.add_batch_file(batch_id, result.file.id, job_id)
            results.append(
                BatchUploadFileResult(
                    file_id=result.file.id,
                    filename=filename,
                    job_id=job_id,
                    status="replaced" if result.replaced else "created",
                )
            )
        except (VaultStoreError, UnicodeDecodeError, ValueError) as exc:
            results.append(
                BatchUploadFileResult(
                    file_id="",
                    filename=filename,
                    job_id=None,
                    status="failed",
                    error_message=str(exc),
                )
            )
            vault_db.refresh_batch_counts(batch_id)

    vault_db.refresh_batch_counts(batch_id)
    return BatchUploadResponse(batch_id=batch_id, files=results)


@router.get("/files/{file_id}", response_model=VaultFile)
def get_file(file_id: str) -> VaultFile:
    try:
        return vault_store.get_file(file_id)
    except VaultStoreError as exc:
        _raise_store(exc)
        raise  # pragma: no cover


@router.get("/files/{file_id}/content")
def get_file_content(file_id: str) -> dict[str, str | int]:
    try:
        content = vault_store.read_file_content(file_id)
        file = vault_store.get_file(file_id)
    except VaultStoreError as exc:
        _raise_store(exc)
        raise  # pragma: no cover
    return {
        "id": file.id,
        "relative_path": file.relative_path,
        "content": content,
        "size": len(content.encode("utf-8")),
    }


@router.put("/files/{file_id}/content", response_model=UploadResponse)
def put_file_content(
    file_id: str, body: SaveContentRequest, request: Request
) -> UploadResponse:
    try:
        file = vault_store.save_file_content(file_id, body.content)
    except VaultStoreError as exc:
        _raise_store(exc)
        raise  # pragma: no cover
    traceparent = request.headers.get("traceparent", "")
    job_id = enqueue_vault_ingest(file.id, traceparent=traceparent)
    return UploadResponse(file=vault_store.get_file(file.id), ingest_job_id=job_id)


@router.delete("/files/batch", response_model=BatchDeleteResult)
def delete_files_batch(body: BatchDeleteRequest) -> BatchDeleteResult:
    results: list[BatchDeleteItem] = []
    for file_id in body.file_ids:
        try:
            vault_store.delete_file(file_id)
            results.append(BatchDeleteItem(file_id=file_id, ok=True))
        except VaultStoreError as exc:
            results.append(
                BatchDeleteItem(file_id=file_id, ok=False, error=str(exc))
            )
    return BatchDeleteResult(results=results)


@router.post("/files/{file_id}/reindex", response_model=ReindexResponse)
def reindex_file(file_id: str, request: Request) -> ReindexResponse:
    try:
        file = vault_store.get_file(file_id)
    except VaultStoreError as exc:
        _raise_store(exc)
        raise  # pragma: no cover
    if file.ingest_locked:
        raise HTTPException(status_code=409, detail="File is locked while ingest is running")
    traceparent = request.headers.get("traceparent", "")
    try:
        job_id = enqueue_vault_ingest(file_id, traceparent=traceparent)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ReindexResponse(
        file_id=file_id,
        relative_path=file.relative_path,
        ingest_job_id=job_id,
    )


@router.post("/sync", response_model=SyncReport)
def post_sync() -> SyncReport:
    return sync_vault()


@router.get("/batches/{batch_id}", response_model=BatchStatusResponse)
def get_batch(batch_id: str) -> BatchStatusResponse:
    batch = vault_db.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    vault_db.refresh_batch_counts(batch_id)
    batch = vault_db.get_batch(batch_id)
    assert batch is not None
    file_rows = vault_db.list_batch_files(batch_id)
    files: list[BatchUploadFileResult] = []
    completed = 0
    failed = 0
    for fr in file_rows:
        status = fr["status"]
        file_row = vault_db.get_file_by_id(fr["file_id"])
        if file_row:
            if file_row["index_status"] == "indexed":
                status = "completed"
                completed += 1
                vault_db.update_batch_file_status(batch_id, fr["file_id"], status="completed")
            elif file_row["index_status"] == "error":
                status = "failed"
                failed += 1
                vault_db.update_batch_file_status(batch_id, fr["file_id"], status="failed")
            elif file_row["index_status"] == "pending":
                status = "pending"
        files.append(
            BatchUploadFileResult(
                file_id=fr["file_id"],
                filename=file_row["filename"] if file_row else fr["file_id"],
                job_id=fr.get("job_id"),
                status=status,
            )
        )
    vault_db.refresh_batch_counts(batch_id)
    batch = vault_db.get_batch(batch_id)
    assert batch is not None
    return BatchStatusResponse(
        id=batch["id"],
        created_at=batch["created_at"],
        total_files=batch["total_files"],
        completed_files=batch["completed_files"],
        failed_files=batch["failed_files"],
        files=files,
    )
