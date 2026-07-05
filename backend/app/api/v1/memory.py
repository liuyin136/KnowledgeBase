"""
api/v1/memory.py — Memory + MemoryCart endpoints.

  • GET    /api/v1/memories               — list (paginated, ?experimentId)
  • POST   /api/v1/memories               — manually create a memory
  • POST   /api/v1/memory-carts           — create a cart
  • GET    /api/v1/memory-carts           — list carts
  • GET    /api/v1/memory-carts/{id}      — get one cart with embedded memories
  • PATCH  /api/v1/memory-carts/{id}      — update name/description OR set/add memory ids
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_db
from app.core.exceptions import NotFoundError, ValidationError
from app.db.neo4j_client import Neo4jClient
from app.models.neo4j_models import Memory, MemoryCart
from app.schemas.common import Paginated
from app.schemas.memory import (
    CreateMemoryCartRequest,
    CreateMemoryRequest,
    MemoryCartDetailResponse,
    MemoryCartResponse,
    MemoryResponse,
    PatchMemoryCartRequest,
)

memories_router = APIRouter(prefix="/memories", tags=["memories"])
carts_router = APIRouter(prefix="/memory-carts", tags=["memory-carts"])


# ─── helpers ──────────────────────────────────────────────────────────────────


def _to_bool(v) -> Optional[bool]:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    return str(v).lower() in ("true", "1", "yes")


def _memory_row_to_response(row: dict) -> MemoryResponse:
    """Coerce a list_memories() row ({memory, selected}) into MemoryResponse."""
    m = row.get("memory") or {}
    ts = m.get("timestamp")
    if hasattr(ts, "isoformat"):
        ts = ts.isoformat()
    return MemoryResponse(
        id=m.get("id", ""),
        userQueryId=m.get("user_query_id", ""),
        experimentId=m.get("experiment_id"),
        chunkId=m.get("chunk_id"),
        queryText=m.get("query_text", ""),
        chunkText=m.get("chunk_text"),
        score=m.get("score"),
        vectorScore=m.get("vector_score"),
        bm25Score=m.get("bm25_score"),
        fusedScore=m.get("fused_score"),
        rerankerScore=m.get("reranker_score"),
        notes=m.get("notes"),
        successScore=m.get("success_score"),
        createdAt=ts or datetime.utcnow(),
        selected=bool(row.get("selected", False)),
    )


def _memory_node_to_response(m: dict) -> MemoryResponse:
    return _memory_row_to_response({"memory": m, "selected": False})


def _cart_row_to_response(row: dict) -> MemoryCartResponse:
    cart = row.get("cart") or {}
    created = cart.get("created_at")
    updated = cart.get("updated_at")
    if hasattr(created, "isoformat"):
        created = created.isoformat()
    if hasattr(updated, "isoformat"):
        updated = updated.isoformat()
    return MemoryCartResponse(
        id=cart.get("id", ""),
        name=cart.get("name", ""),
        description=cart.get("description"),
        memoryCount=int(row.get("memory_count") or 0),
        createdAt=created or datetime.utcnow(),
        updatedAt=updated or datetime.utcnow(),
    )


# ─── Memories ─────────────────────────────────────────────────────────────────


@memories_router.get("", response_model=Paginated[MemoryResponse])
def list_memories(
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
    db: Neo4jClient = Depends(get_db),
) -> Paginated[MemoryResponse]:
    rows, total = db.list_memories(page=page, page_size=pageSize)
    return Paginated[MemoryResponse](
        items=[_memory_row_to_response(r) for r in rows],
        total=total,
        page=page,
        pageSize=pageSize,
        hasMore=(page * pageSize) < total,
    )


@memories_router.post("", response_model=dict, status_code=201)
def create_memory(
    body: CreateMemoryRequest,
    db: Neo4jClient = Depends(get_db),
) -> dict:
    memory = Memory(
        id=str(uuid.uuid4()),
        user_query_id=body.userQueryId,
        timestamp=datetime.utcnow(),
        success_score=None,
        notes=body.notes,
        query_text=body.queryText,
        chunk_id=body.chunkId,
        chunk_text=body.chunkText,
        score=body.score,
        vector_score=body.vectorScore,
        bm25_score=body.bm25Score,
        fused_score=body.fusedScore,
        reranker_score=body.rerankerScore,
        # experiment_id removed
        # experiment_id=body.experimentId,
    )
    db.create_memory(memory)
    return {"id": memory.id}


# ─── Memory Carts ─────────────────────────────────────────────────────────────


@carts_router.post("", response_model=dict, status_code=201)
def create_cart(
    body: CreateMemoryCartRequest,
    db: Neo4jClient = Depends(get_db),
) -> dict:
    cart = MemoryCart(
        id=str(uuid.uuid4()),
        name=body.name,
        description=body.description,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.create_memory_cart(cart)
    return {"id": cart.id}


@carts_router.get("", response_model=dict)
def list_carts(
    db: Neo4jClient = Depends(get_db),
) -> dict:
    """List all carts. Returns {items: MemoryCartResponse[], total: int}."""
    rows = db.list_memory_carts()
    items = [_cart_row_to_response(r) for r in rows]
    return {"items": items, "total": len(items)}


@carts_router.get("/{cart_id}", response_model=MemoryCartDetailResponse)
def get_cart(
    cart_id: str,
    db: Neo4jClient = Depends(get_db),
) -> MemoryCartDetailResponse:
    row = db.get_memory_cart(cart_id)
    if not row:
        raise NotFoundError(
            f"Memory cart {cart_id} not found",
            details={"cart_id": cart_id},
        )
    cart = row.get("cart") or {}
    memories_raw = row.get("memories") or []
    memories = [_memory_node_to_response(m) for m in memories_raw if m]
    created = cart.get("created_at")
    updated = cart.get("updated_at")
    if hasattr(created, "isoformat"):
        created = created.isoformat()
    if hasattr(updated, "isoformat"):
        updated = updated.isoformat()
    return MemoryCartDetailResponse(
        id=cart.get("id", ""),
        name=cart.get("name", ""),
        description=cart.get("description"),
        memoryCount=len(memories),
        createdAt=created or datetime.utcnow(),
        updatedAt=updated or datetime.utcnow(),
        memories=memories,
    )


@carts_router.patch("/{cart_id}", response_model=MemoryCartDetailResponse)
def patch_cart(
    cart_id: str,
    body: PatchMemoryCartRequest,
    db: Neo4jClient = Depends(get_db),
) -> MemoryCartDetailResponse:
    # Verify existence
    existing = db.get_memory_cart(cart_id)
    if not existing:
        raise NotFoundError(
            f"Memory cart {cart_id} not found",
            details={"cart_id": cart_id},
        )

    # Update name/description if provided (description can be intentionally nulled)
    if body.name is not None or body.description is not None:
        db.update_memory_cart(
            cart_id,
            name=body.name,
            description=body.description,
        )

    # Replace OR add memory ids
    if body.memoryIds is not None:
        db.replace_cart_memories(cart_id, body.memoryIds)
    if body.addMemoryIds:
        db.add_cart_memories(cart_id, body.addMemoryIds)

    db.touch_cart(cart_id)

    # Return the updated cart (re-fetch)
    return get_cart(cart_id, db)  # type: ignore[arg-type]
