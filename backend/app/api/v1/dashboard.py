"""
api/v1/dashboard.py — Dashboard endpoint.

  • GET /api/v1/dashboard → {stats, recentExperiments, recentSearches, system}

The Next.js proxy at /api/v1/dashboard calls this AND adds Neo4j + backend
health checks (so the Dashboard shows connection status). Here we return
stats + recent lists + a `system` info card; the proxy layers `health` on top.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import get_db
from app.api.v1.experiments import _exp_to_response
from app.core.constants import EMBEDDING_DIM, EMBEDDING_MODEL
from app.db.neo4j_client import Neo4jClient

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
def get_dashboard(
    db: Neo4jClient = Depends(get_db),
) -> dict:
    stats = db.dashboard_stats()
    recent_experiments = db.recent_experiments(limit=5)
    recent_searches = db.recent_searches(limit=5)
    return {
        "stats": stats,
        "recentExperiments": [_exp_to_response(e).model_dump(mode="json") for e in recent_experiments],
        "recentSearches": [_exp_to_response(e).model_dump(mode="json") for e in recent_searches],
        "system": {
            "embeddingModel": f"{EMBEDDING_MODEL} (FastAPI backend, GPU)",
            "embeddingDim": EMBEDDING_DIM,
            "stack": "FastAPI + Neo4j 5.x + Redis + Next.js 16 (v1.2 — real directive stack)",
            "v1Scope": (
                "Standard paths only — no Late/Agentic Chunking, no Structured Chat, "
                "no GraphRAG, no multi-user"
            ),
        },
    }
