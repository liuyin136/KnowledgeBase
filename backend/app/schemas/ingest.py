"""
schemas/ingest.py — Ingest request/response + progress event + ChunkMetadata.

Mirrors the TS interfaces IngestConfig (re-exported here for the ingest endpoint
payload), IngestProgressEvent, ChunkMetadata, and the JobStatusResponse shape
(the shared JobStatusResponse type lives in this module to avoid a circular
import with schemas/search.py).
"""

from __future__ import annotations

from typing import List, Optional, Union

from pydantic import BaseModel, Field

from app.core.constants import AdvOption, ChunkMethod, EmbeddingApproach, JobStatus, JobType
from app.schemas.experiment import IngestConfig


class StartIngestRequest(BaseModel):
    documentId: str = Field(..., description="Logical document id (source_file-derived)")
    config: IngestConfig
    experimentDescription: Optional[str] = None


class StartIngestResponse(BaseModel):
    jobId: str
    experimentId: str
    status: str = "queued"


class ChunkMetadata(BaseModel):
    """ChunkMetadata — mirrors TS ChunkMetadata + extensions for full visibility.

    text: full text of the chunk or parent knowledge (for inspector + reconstruction
          in Experiments page). Previously only preview was sent; we now include
          the authoritative stored text so raw/ingested content is visible.
    nodeType: 'knowledge' | 'knowledge_chunk' | 'upload' (for UI labeling of
              raw uploaded :Knowledge vs ingested parent vs children).
    """

    chunkId: str
    parentDocId: str
    experimentId: str
    chunkIndex: int
    chunkMethod: str
    embeddingMethod: str
    tokenCount: int
    chunkingTimeMs: float
    embeddingTimeMs: float
    charStart: Optional[int] = None
    charEnd: Optional[int] = None
    section: Optional[str] = None
    textPreview: str
    # New for raw/parent visibility + mutation-safety clarity in UI
    text: Optional[str] = None
    nodeType: Optional[str] = None  # 'knowledge' | 'knowledge_chunk' | 'upload' (future)
    parentSourceFile: Optional[str] = None


class IngestProgressEvent(BaseModel):
    """IngestProgressEvent — mirrors TS IngestProgressEvent exactly."""

    index: int
    total: int
    progress: float  # 0-100
    chunk: Optional[ChunkMetadata] = None  # null for non-chunk events (start/done)
    stage: str  # "chunking" | "embedding" | "persisting" | "done" | "error"
    message: Optional[str] = None


# Forward declaration — the JobStatusResponse.result field holds a SearchResponse
# for search jobs. We use a forward ref + model_rebuild() at the bottom of
# schemas/search.py to avoid a circular import.
class JobStatusResponse(BaseModel):
    """JobStatusResponse — mirrors TS JobStatusResponse exactly."""

    jobId: str
    type: JobType
    experimentId: Optional[str] = None
    status: JobStatus
    progress: float
    current: int
    total: int
    events: List[IngestProgressEvent] = Field(default_factory=list)
    errorCode: Optional[str] = None
    errorMessage: Optional[str] = None
    result: Optional["SearchResponse"] = None  # noqa: F821 — for search jobs


# Re-export IngestConfig for convenience
__all__ = [
    "IngestConfig",
    "StartIngestRequest",
    "StartIngestResponse",
    "ChunkMetadata",
    "IngestProgressEvent",
    "JobStatusResponse",
]
