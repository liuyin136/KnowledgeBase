"""Pydantic schemas for the RAG Content Vault API."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

IndexStatus = Literal[
    "not_indexed",
    "pending",
    "indexed",
    "modified",
    "error",
    "deleted",
]

PAGE_SIZES = {5, 10, 20}


class VaultFolder(BaseModel):
    id: str
    name: str
    slug: str
    created_at: str
    relative_path: str
    file_count: int = 0


class FolderRenamePreviewFile(BaseModel):
    old_relative_path: str
    new_relative_path: str
    index_status: IndexStatus


class FolderRenamePreview(BaseModel):
    folder_id: str
    old_name: str
    new_name: str
    old_slug: str
    new_slug: str
    slug_unchanged: bool
    can_rename: bool
    block_reason: str | None = None
    total_files: int
    neo4j_knowledge_count: int
    preview_files: list[FolderRenamePreviewFile]
    has_more_files: bool


class CreateFolderRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class RenameFolderRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class VaultFile(BaseModel):
    id: str
    folder_id: str
    filename: str
    relative_path: str
    source: str
    created_at: str
    updated_at: str
    size_bytes: int
    mime_ext: str
    mutable: bool
    index_status: IndexStatus
    chunk_count: int
    last_ingest_job_id: str | None = None
    last_ingest_at: str | None = None
    ingest_locked: bool = False
    error_message: str | None = None
    content_preview: str | None = None


class PaginatedFilesResponse(BaseModel):
    files: list[VaultFile]
    total: int
    page: int
    page_size: int
    total_pages: int


class CreateFileRequest(BaseModel):
    folder_id: str
    filename: str = Field(min_length=1, max_length=255)
    content: str = ""


class SaveContentRequest(BaseModel):
    content: str


class BatchDeleteRequest(BaseModel):
    file_ids: list[str] = Field(min_length=1)


class BatchDeleteItem(BaseModel):
    file_id: str
    ok: bool
    error: str | None = None


class BatchDeleteResult(BaseModel):
    results: list[BatchDeleteItem]


class SyncReport(BaseModel):
    files_scanned: int
    drift_added: int
    drift_modified: int
    drift_removed: int
    last_sync_at: str | None = None


class ReindexResponse(BaseModel):
    file_id: str
    relative_path: str
    ingest_job_id: str


class IngestPreviewRequest(BaseModel):
    file_ids: list[str] = Field(min_length=1)


class IngestPreviewItem(BaseModel):
    file_id: str
    relative_path: str
    estimated_tokens: int
    ingestible: bool
    block_reason: str | None = None


class IngestPreviewResponse(BaseModel):
    items: list[IngestPreviewItem]
    total_estimated_tokens: int
    file_count: int


class BatchIngestRequest(BaseModel):
    file_ids: list[str] = Field(min_length=1)


class BatchIngestSkippedItem(BaseModel):
    file_id: str
    reason: str


class BatchIngestResponse(BaseModel):
    batch_id: str
    queued: list[str]
    skipped: list[BatchIngestSkippedItem]


class ClearIndexResponse(BaseModel):
    file_id: str
    relative_path: str
    index_status: IndexStatus


class MigrateV16JobEntry(BaseModel):
    file_id: str
    relative_path: str
    ingest_job_id: str


class MigrateV16Response(BaseModel):
    total_files: int
    job_ids: list[MigrateV16JobEntry]
    dry_run: bool = False
    neo4j_stats: dict[str, int] = Field(default_factory=dict)
    redis_keys_deleted: int = 0


class UploadResponse(BaseModel):
    file: VaultFile
    ingest_job_id: str | None = None
    replaced: bool = False


class BatchUploadFileResult(BaseModel):
    file_id: str
    filename: str
    job_id: str | None = None
    status: str
    error_message: str | None = None


class BatchUploadResponse(BaseModel):
    batch_id: str
    files: list[BatchUploadFileResult]


class BatchStatusResponse(BaseModel):
    id: str
    created_at: str
    total_files: int
    completed_files: int
    failed_files: int
    files: list[BatchUploadFileResult]


class FolderListResponse(BaseModel):
    folders: list[VaultFolder]


def validate_page_size(page_size: int) -> int:
    if page_size not in PAGE_SIZES:
        raise ValueError(f"page_size must be one of {sorted(PAGE_SIZES)}")
    return page_size


class FileListQuery(BaseModel):
    folder_id: str | None = None
    keyword: str | None = None
    index_status: IndexStatus | None = None
    search_content: bool = False
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10)

    @field_validator("page_size")
    @classmethod
    def check_page_size(cls, v: int) -> int:
        return validate_page_size(v)
