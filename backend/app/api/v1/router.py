"""
api/v1/router.py — Aggregate all v1 routers under /api/v1.

Import order matters for route precedence (FastAPI matches in registration
order). Sub-routers with longer/more-specific prefixes are registered first.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    dashboard,
    documents,
    ingest,
    jobs,
    memory,
    search,
)

api_router = APIRouter(prefix="/api/v1")

# Register all v1 sub-routers. Each sub-router already has its own prefix
# (e.g. experiments.router has prefix="/experiments"), so we just include them.
api_router.include_router(documents.router)
api_router.include_router(ingest.router)
api_router.include_router(search.router)
api_router.include_router(memory.memories_router)
api_router.include_router(memory.carts_router)
api_router.include_router(jobs.router)
api_router.include_router(dashboard.router)
