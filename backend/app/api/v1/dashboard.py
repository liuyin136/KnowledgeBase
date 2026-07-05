"""
api/v1/dashboard.py — Dashboard endpoint.

  • GET /api/v1/dashboard → {stats, recentExperiments, recentSearches, system}

The Next.js proxy at /api/v1/dashboard calls this AND adds Neo4j + backend
health checks (so the Dashboard shows connection status). Here we return
stats + recent lists + a `system` info card; the proxy layers `health` on top.

v1.3: the `system` card now reports the ACTIVE embedding + reranker model
(repo id + logical id + native dim) so the frontend Settings view can show
which model is currently loaded and how to switch.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import get_db
from app.api.v1.experiments import _exp_to_response
from app.core.config import settings
from app.core.constants import EMBEDDING_DIM
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
            "embeddingModel": settings.embedding_repo,
            "embeddingModelLogical": settings.embedding_model,
            "embeddingDim": EMBEDDING_DIM,  # actual dim written to Neo4j (1024 for both)
            "embeddingNativeDim": settings.model_dim,  # native dim (Jina v5 small = 1536, BGE-M3 = 1024)
            "rerankerModel": settings.reranker_repo,
            "rerankerModelLogical": settings.reranker_model,
            "rerankerMaxLength": settings.reranker_max_length,
            "stack": "FastAPI + Neo4j 5.x + Redis + Next.js 16 (v1.3 — Jina v5 default + BGE-M3 toggle)",
            "v1Scope": (
                "Standard paths only — no Late/Agentic Chunking, no Structured Chat, "
                "no GraphRAG, no multi-user"
            ),
        },
    }
