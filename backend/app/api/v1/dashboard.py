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
from app.core.config import settings
from app.core.constants import EMBEDDING_DIM
from app.core.logging import get_logger, log_pipeline_event
from app.db.neo4j_client import Neo4jClient

logger = get_logger("rag.api.dashboard")


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
def get_dashboard(
    db: Neo4jClient = Depends(get_db),
) -> dict:
    stats = db.dashboard_stats()
    # recent experiments/searches removed (no :Experiment node)
    resp = {
        "stats": stats,
        "recentExperiments": [],
        "recentSearches": [],
        "system": {
            "embeddingModel": settings.embedding_repo,
            "embeddingModelLogical": settings.embedding_model,
            "embeddingDim": EMBEDDING_DIM,
            "embeddingNativeDim": settings.model_dim,
            "rerankerModel": settings.reranker_repo,
            "rerankerModelLogical": settings.reranker_model,
            "rerankerMaxLength": settings.reranker_max_length,
            "stack": "FastAPI + Neo4j 5.x + Redis + Next.js 16 (Jina-embeddings-v5-text-small ONLY)",
            "v1Scope": (
                "Standard paths only — no Late/Agentic Chunking, no Structured Chat, "
                "no GraphRAG, no multi-user"
            ),
        },
    }
    # observation: end of Dashboard flow - what stats (exp/docs numbers) + recent are sent to UI (from neo4j via proxy)
    log_pipeline_event(logger, "dashboard.response", "dashboard response to proxy", stats=stats, recent_exp_count=len(resp["recentExperiments"]))
    return resp
