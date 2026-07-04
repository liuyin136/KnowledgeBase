"""
schemas/common.py — Shared Pydantic models (ErrorResponse, Paginated).

Mirrors the TS `ErrorBody` + `Paginated<T>` interfaces in src/lib/rag/types.ts.
"""

from __future__ import annotations

from typing import Any, Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorPayload(BaseModel):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


class ErrorResponse(BaseModel):
    error: ErrorPayload


class Paginated(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    pageSize: int
    hasMore: bool


class OkResponse(BaseModel):
    ok: bool = True
