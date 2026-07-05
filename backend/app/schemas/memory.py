"""
schemas/memory.py — Memory + MemoryCart request/response models.

Mirrors the TS Memory + MemoryCart interfaces in src/lib/rag/types.ts.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class MemoryResponse(BaseModel):
    """Memory — mirrors TS Memory exactly."""

    id: str
    userQueryId: str
    experimentId: Optional[str] = None
    chunkId: Optional[str] = None
    queryText: str
    chunkText: Optional[str] = None
    score: Optional[float] = None
    vectorScore: Optional[float] = None
    bm25Score: Optional[float] = None
    fusedScore: Optional[float] = None
    rerankerScore: Optional[float] = None
    notes: Optional[str] = None
    successScore: Optional[float] = None
    createdAt: datetime
    selected: bool = False  # whether currently in a cart (denormalized for UI)


class CreateMemoryRequest(BaseModel):
    userQueryId: str
    queryText: str
    chunkId: Optional[str] = None
    chunkText: Optional[str] = None
    notes: Optional[str] = None
    score: Optional[float] = None
    vectorScore: Optional[float] = None
    bm25Score: Optional[float] = None
    fusedScore: Optional[float] = None
    rerankerScore: Optional[float] = None
    experimentId: Optional[str] = None


class MemoryCartResponse(BaseModel):
    """MemoryCart — mirrors TS MemoryCart exactly."""

    id: str
    name: str
    description: Optional[str] = None
    memoryCount: int = 0
    createdAt: datetime
    updatedAt: datetime


class MemoryCartDetailResponse(MemoryCartResponse):
    """MemoryCart with embedded memories (for GET /[id])."""

    memories: List[MemoryResponse] = Field(default_factory=list)


class CreateMemoryCartRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    description: Optional[str] = Field(default=None, max_length=2048)


class PatchMemoryCartRequest(BaseModel):
    """PATCH /memory-carts/[id] — all fields optional.

    `memoryIds` REPLACES the cart's contents; `addMemoryIds` ADDS to it.
    """

    name: Optional[str] = Field(default=None, min_length=1, max_length=256)
    description: Optional[str] = Field(default=None, max_length=2048)
    memoryIds: Optional[List[str]] = None
    addMemoryIds: Optional[List[str]] = None
