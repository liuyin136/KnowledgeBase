from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["RND", "Daily", "case"]
IndexStatus = Literal["pending", "indexed", "error", "not_indexed"]


class FileListItem(BaseModel):
    path: str
    name: str
    category: Category
    modified_at: float
    index_status: IndexStatus = "not_indexed"
    indexed_at: str | None = None
    last_ingest_job_id: str | None = None
    chunk_count: int = 0


class FileListResponse(BaseModel):
    files: list[FileListItem]
    total: int


class FileContentResponse(BaseModel):
    path: str
    content: str
    size: int
    ingest_job_id: str | None = None


class SaveContentRequest(BaseModel):
    path: str
    content: str


class CreateLogRequest(BaseModel):
    category: Category
    title: str = Field(min_length=1)
    environment: str = ""
    execution_step: str = ""
    results: str = ""
    next_steps: str = ""
    symptom: str = ""
    error_log: str = ""
    investigation: str = ""
    solution: str = ""
    note: str = ""
    done: str = ""
    todo: str = ""
    blocker: str = ""


class CreateLogResponse(BaseModel):
    path: str
    content: str
    job_id: str | None = None
    ingest_job_id: str | None = None


class ReindexResponse(BaseModel):
    ingest_job_id: str
    span_id: str
