"""
schemas/document.py — Document upload + list models.

Documents are stored in Neo4j as :Knowledge nodes (per ingest run). The
`/documents` endpoint serves a logical "unique source files" view derived
from the Knowledge graph so the frontend's Upload + DocumentsListCard flow
works against the FastAPI backend unchanged.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CreateDocumentRequest(BaseModel):
    """JSON document upload body (mirrors api.documents.create body)."""

    filename: str = Field(..., min_length=1, max_length=512)
    text: str = Field(..., min_length=1)
    contentType: Optional[str] = Field(default="text/plain")


class DocumentItem(BaseModel):
    """Logical document (one per unique source_file)."""

    id: str
    filename: str
    contentType: str
    sizeBytes: int
    totalChunks: int
    createdAt: datetime


class DocumentCreatedResponse(BaseModel):
    id: str
