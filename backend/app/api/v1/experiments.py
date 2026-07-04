"""
api/v1/experiments.py — Experiment CRUD + chunk observability endpoints.

  • POST   /api/v1/experiments                 — create a new experiment record
  • GET    /api/v1/experiments                 — list (paginated, ?kind=ingest|search)
  • GET    /api/v1/experiments/{id}            — get one
  • GET    /api/v1/experiments/{id}/chunks     — list chunks for observability

Mirrors the Next.js proxy routes exactly so the frontend works unchanged.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_db
from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.neo4j_client import Neo4jClient
from app.schemas.common import Paginated
from app.schemas.experiment import (
    CreateExperimentRequest,
    ExperimentResponse,
    IngestConfig,
)
from app.schemas.ingest import ChunkMetadata
from app.utils.tokenization import preview

router = APIRouter(prefix="/experiments", tags=["experiments"])
logger = get_logger("rag.api.experiments")


def _exp_to_response(e: dict) -> ExperimentResponse:
    """Coerce a Neo4j Experiment node (snake_case) into the camelCase response."""
    return ExperimentResponse(
        id=e.get("id", ""),
        description=e.get("description", ""),
        embeddingApproach=e.get("embedding_approach", ""),
        chunkMethod=e.get("chunk_method", ""),
        totalChunks=int(e.get("total_chunks") or 0),
        avgTokensPerChunk=float(e.get("avg_tokens_per_chunk") or 0.0),
        totalTimeMs=float(e.get("total_time_ms") or 0.0),
        sourceFile=e.get("source_file", ""),
        createdAt=e.get("created_at"),
        status=e.get("status", "pending"),
        errorCode=e.get("error_code"),
        errorMessage=e.get("error_message"),
        hybridAlpha=e.get("hybrid_alpha"),
        useBm25=_to_bool(e.get("use_bm25")),
        useReranker=_to_bool(e.get("use_reranker")),
        topKVector=_to_int(e.get("top_k_vector")),
        topNRerank=_to_int(e.get("top_n_rerank")),
        parentContextLevels=_to_int(e.get("parent_context_levels")),
        autoTuneWeights=_to_bool(e.get("auto_tune_weights")),
        bestAlpha=e.get("best_alpha"),
        rawQuery=e.get("raw_query"),
        kind=e.get("kind", "ingest"),
    )


def _to_bool(v) -> Optional[bool]:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    return str(v).lower() in ("true", "1", "yes")


def _to_int(v) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _chunk_to_response(c: dict, experiment_id: str) -> ChunkMetadata:
    """Coerce a KnowledgeChunk OR LongText Knowledge node into ChunkMetadata."""
    # For LongText windows (no parent child), parent_doc_id = self.id.
    parent_doc_id = c.get("parent_doc_id") or c.get("id", "")
    chunk_id = c.get("id", "")
    chunk_method = c.get("chunk_method") or c.get("embedding_method", "")
    embedding_method = c.get("embedding_method", "")
    text = c.get("text", "")
    return ChunkMetadata(
        chunkId=chunk_id,
        parentDocId=parent_doc_id,
        experimentId=experiment_id,
        chunkIndex=int(c.get("chunk_index") or 0),
        chunkMethod=chunk_method,
        embeddingMethod=embedding_method,
        tokenCount=int(c.get("token_count") or 0),
        chunkingTimeMs=float(c.get("chunking_time_ms") or 0.0),
        embeddingTimeMs=float(c.get("embedding_time_ms") or 0.0),
        charStart=c.get("char_start"),
        charEnd=c.get("char_end"),
        section=c.get("section"),
        textPreview=preview(text, 220),
    )


@router.post("", response_model=ExperimentResponse, status_code=201)
def create_experiment(
    body: CreateExperimentRequest,
    db: Neo4jClient = Depends(get_db),
) -> ExperimentResponse:
    """Create a new experiment record (without running it).

    Used by the frontend's experiment-creation flow. The actual ingest/search
    is triggered separately via /ingest or /search.
    """
    import uuid
    from datetime import datetime

    from app.models.neo4j_models import Experiment

    config: Optional[IngestConfig] = body.config
    exp = Experiment(
        id=str(uuid.uuid4()),
        description=body.description,
        embedding_approach=config.embeddingApproach.value if config else "LongText",
        chunk_method=config.chunkMethod.value if config else "LongText",
        total_chunks=0,
        avg_tokens_per_chunk=0.0,
        total_time_ms=0.0,
        source_file=body.sourceFile or "",
        created_at=datetime.utcnow(),
        status="pending",
        kind="ingest",
    )
    db.create_experiment(exp)
    return _exp_to_response(exp.model_dump())


@router.get("", response_model=Paginated[ExperimentResponse])
def list_experiments(
    kind: Optional[str] = Query(default=None, description="ingest | search"),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
    db: Neo4jClient = Depends(get_db),
) -> Paginated[ExperimentResponse]:
    items, total = db.list_experiments(kind=kind, page=page, page_size=pageSize)
    return Paginated[ExperimentResponse](
        items=[_exp_to_response(i) for i in items],
        total=total,
        page=page,
        pageSize=pageSize,
        hasMore=(page * pageSize) < total,
    )


@router.get("/{experiment_id}", response_model=ExperimentResponse)
def get_experiment(
    experiment_id: str,
    db: Neo4jClient = Depends(get_db),
) -> ExperimentResponse:
    e = db.get_experiment(experiment_id)
    if not e:
        raise NotFoundError(
            f"Experiment {experiment_id} not found",
            details={"experiment_id": experiment_id},
        )
    return _exp_to_response(e)


@router.get("/{experiment_id}/chunks")
def get_experiment_chunks(
    experiment_id: str,
    db: Neo4jClient = Depends(get_db),
) -> dict:
    """Return all chunks for an experiment (observability).

    Returns `{items: ChunkMetadata[], total: int}` to match the Next.js proxy.
    """
    # Verify the experiment exists
    e = db.get_experiment(experiment_id)
    if not e:
        raise NotFoundError(
            f"Experiment {experiment_id} not found",
            details={"experiment_id": experiment_id},
        )
    chunks = db.list_chunks_for_experiment(experiment_id)
    items = [_chunk_to_response(c, experiment_id) for c in chunks]
    return {"items": items, "total": len(items)}
