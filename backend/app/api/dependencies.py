"""
api/dependencies.py — FastAPI dependency providers.

Singletons are constructed at app startup (lifespan) and exposed via Depends.
"""

from __future__ import annotations

from typing import Optional

from app.db.neo4j_client import Neo4jClient, get_neo4j_client
from app.services.embedding import EmbeddingModule, get_embedder
from app.workers.progress import ProgressTracker, get_progress_tracker


def get_db() -> Neo4jClient:
    """Yield the Neo4jClient singleton."""
    return get_neo4j_client()


def get_embedding_module() -> EmbeddingModule:
    """Yield the EmbeddingModule singleton."""
    return get_embedder()


def get_job_tracker() -> ProgressTracker:
    """Yield the ProgressTracker singleton."""
    return get_progress_tracker()
