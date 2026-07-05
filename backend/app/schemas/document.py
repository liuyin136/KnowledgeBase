"""
schemas/document.py — Document upload + list models.

Supports:
- JSON body for single doc (paste / edit-save flows)
- Multipart with one or more 'file' fields for .md uploads (primary new mechanism)

The `/documents` endpoint serves a logical "unique source files" view.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

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
    # Extras for UI (badges distinguishing Upload vs LongText ingested :Knowledge)
    representativeEmbeddingMethod: Optional[str] = None
    kinds: Optional[List[str]] = None


class DocumentCreatedResponse(BaseModel):
    """Batch-friendly response for document creation (supports multi-file uploads).

    ids always contains the created source_file identifiers (one or more).
    """
    ids: List[str]
