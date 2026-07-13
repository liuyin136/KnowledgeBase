"""REST schemas for memory extract API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class MemoryExtractRequest(BaseModel):
    query_text: str = Field(min_length=1)
    grandchild_ids: list[str] = Field(min_length=1)
    user_query_id: str | None = None
    session_id: str | None = None


class MemoryExtractResponse(BaseModel):
    job_id: str
    trace_id: str


class MemoryBundleResponse(BaseModel):
    memory_key: str
    memory_id: str | None = None
    content: str | None = None
    version: int = 0
    entity_count: int = 0
    claim_count: int = 0
    community_count: int = 0
    grandchild_count: int = 0
