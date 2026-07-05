"""
schemas/search.py — Search request/response + metadata + result models.

Mirrors the TS interfaces SearchConfig, SearchResult, SearchMetadata,
SearchResponse in src/lib/rag/types.ts EXACTLY (camelCase keys, optional
fields, score types).

Construction note #2: SearchConfig.autoTuneWeights enables the adaptive
alpha/beta sweep in services/retrieval.py; SearchMetadata.bestAlpha carries
the chosen alpha back to the client.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class SearchConfig(BaseModel):
    """SearchConfig — mirrors TS SearchConfigSchema exactly."""

    hybridAlpha: float = Field(default=0.7, ge=0.0, le=1.0)
    useBm25: bool = True
    topKVector: int = Field(default=10, ge=1, le=100)
    topNRerank: int = Field(default=5, ge=0, le=50)
    useReranker: bool = False
    parentContextLevels: int = Field(default=1, ge=0, le=5)
    # Construction note #2: adaptive alpha/beta sweep (0.1–0.9).
    autoTuneWeights: bool = False


class StartSearchRequest(BaseModel):
    rawQuery: str = Field(..., min_length=1)
    config: SearchConfig
    experimentId: Optional[str] = None


class StartSearchResponse(BaseModel):
    jobId: str
    searchId: str
    status: str = "queued"


class SearchResult(BaseModel):
    """SearchResult — mirrors TS SearchResult exactly."""

    rank: int
    chunkId: str
    parentId: str
    experimentId: str
    chunkIndex: int
    text: str
    tokenCount: int
    chunkMethod: str
    embeddingMethod: str
    parentSourceFile: str
    parentTextPreview: str
    # Scores
    vectorScore: float
    bm25Score: Optional[float] = None
    fusedScore: float
    rerankerScore: Optional[float] = None
    finalScore: float
    # Config snapshot used (for observability)
    alphaUsed: float
    betaUsed: float
    # Context
    section: Optional[str] = None
    chunkingTimeMs: float
    embeddingTimeMs: float


class SearchMetadata(BaseModel):
    """SearchMetadata — mirrors TS SearchMetadata exactly."""

    searchId: str
    experimentId: Optional[str] = None
    queryEmbeddingTimeMs: float
    vectorSearchTimeMs: float
    bm25SearchTimeMs: float
    rerankTimeMs: float
    totalSearchTimeMs: float
    config: SearchConfig
    bestAlpha: Optional[float] = None  # when autoTuneWeights
    candidatesBeforeRerank: int
    resultsAfterRerank: int


class SearchResponse(BaseModel):
    """SearchResponse — mirrors TS SearchResponse exactly."""

    searchId: str
    results: List[SearchResult]
    metadata: SearchMetadata


# Rebuild the forward reference in schemas/ingest.py (JobStatusResponse.result
# is typed as Optional[SearchResponse]). We pass an explicit types namespace so
# pydantic can resolve `SearchResponse` regardless of which module's globals it
# would otherwise consult (the class is defined in search.py but the forward
# reference lives in ingest.py — explicit namespace avoids lookup ambiguity).
from app.schemas.ingest import JobStatusResponse  # noqa: E402

JobStatusResponse.model_rebuild(_types_namespace={"SearchResponse": SearchResponse})
