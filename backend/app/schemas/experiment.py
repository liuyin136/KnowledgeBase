"""
schemas/experiment.py — Experiment request/response models (in-memory run metadata).

Mirrors the ExperimentRun interface in src/lib/rag/types.ts.
No :Experiment node in Neo4j (removed); these are pure correlation + observability DTOs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.core.constants import AdvOption, ChunkMethod, EmbeddingApproach, ExperimentKind, ExperimentStatus


class IngestConfig(BaseModel):
    """IngestConfig — mirrors TS IngestConfigSchema exactly."""

    embeddingApproach: EmbeddingApproach = Field(..., description="LongText | ChildChunk")
    chunkMethod: ChunkMethod = Field(..., description="Recursive | Semantic | Structure-Aware")
    advOption: AdvOption = Field(default=AdvOption.NONE, description="v1 always 'None'")


class CreateExperimentRequest(BaseModel):
    description: str
    config: Optional[IngestConfig] = None
    sourceFile: Optional[str] = None


class ExperimentResponse(BaseModel):
    """Full experiment record shape (for API compat; not backed by :Experiment node)."""

    id: str
    description: str
    embeddingApproach: str
    chunkMethod: str
    totalChunks: int
    avgTokensPerChunk: float
    totalTimeMs: float
    sourceFile: str
    createdAt: datetime
    status: ExperimentStatus
    errorCode: Optional[str] = None
    errorMessage: Optional[str] = None
    # Search-specific
    hybridAlpha: Optional[float] = None
    useBm25: Optional[bool] = None
    useReranker: Optional[bool] = None
    topKVector: Optional[int] = None
    topNRerank: Optional[int] = None
    parentContextLevels: Optional[int] = None
    autoTuneWeights: Optional[bool] = None
    bestAlpha: Optional[float] = None
    rawQuery: Optional[str] = None
    kind: ExperimentKind = ExperimentKind.INGEST


class ExperimentRunMetadata(BaseModel):
    """ExperimentRun (metadata contract per Backend §6)."""

    experimentId: str
    description: str
    embeddingApproach: str
    chunkMethod: str
    totalChunks: int
    avgTokensPerChunk: float
    totalTimeMs: float
    sourceFile: str
    status: ExperimentStatus
