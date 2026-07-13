from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.constants import ALLOWED_COARSE_DIMS_V1


SearchJobStatus = Literal["awaiting_rerank", "finished", "skipped_rerank", "rerank_started"]


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    w1: float = Field(default=0.7, ge=0.0, le=1.0)
    w2: float = Field(default=0.3, ge=0.0, le=1.0)
    recall_k: int = Field(default=50, ge=1, le=200)
    rerank_k: int = Field(default=10, ge=1, le=50)
    coarse_dim: int = Field(default=256)
    use_minmax_fallback: bool = False
    folder_ids: list[str] | None = None
    created_after: date | None = None
    created_before: date | None = None
    indexed_only: bool = True

    @field_validator("coarse_dim")
    @classmethod
    def validate_coarse_dim(cls, v: int) -> int:
        if v not in ALLOWED_COARSE_DIMS_V1:
            raise ValueError(f"coarse_dim must be one of {ALLOWED_COARSE_DIMS_V1}")
        return v

    @model_validator(mode="after")
    def validate_weight_sum(self) -> "SearchRequest":
        if abs(self.w1 + self.w2 - 1.0) > 1e-6:
            raise ValueError("w1 + w2 must equal 1.0")
        return self

    @model_validator(mode="after")
    def validate_date_range(self) -> "SearchRequest":
        if (
            self.created_after is not None
            and self.created_before is not None
            and self.created_after > self.created_before
        ):
            raise ValueError("created_after must be on or before created_before")
        return self


class SearchHit(BaseModel):
    chunk_id: str
    parent_path: str
    chunk_index: int
    content_preview: str
    final_score: float
    display_score: float
    vector_score: float = 0.0
    rerank_score: float | None = None
    file_id: str | None = None
    index_status: str | None = None
    relative_path: str | None = None
    parent_id: str | None = None
    child_id: str | None = None
    family_id: str | None = None
    parent_content: str | None = None
    header_path: str | None = None


class FusionMeta(BaseModel):
    pool_size: int
    w1: float
    w2: float
    recall_k: int
    rerank_k: int
    coarse_dim: int
    rescore_dim: int = 1024
    latency_ms: int
    vector_hit_count: int = 0
    bm25_hit_count: int = 0
    vram_peak_mb: int = 0
    folder_ids: list[str] | None = None
    created_after: str | None = None
    created_before: str | None = None
    indexed_only: bool | None = None
    allowlist_size: int | None = None
    rerank_over_limit: bool | None = None


WorkflowPhaseName = Literal[
    "vault_scope",
    "query_embed",
    "family_recall",
    "parent_recall",
    "child_recall",
    "grandchild_recall",
    "hierarchical_fusion",
    "rerank",
    # Legacy phases kept for cached/old jobs
    "coarse_ann",
    "bm25_recall",
    "rescore_1024",
    "hybrid_fusion",
]


class WorkflowPhase(BaseModel):
    phase: WorkflowPhaseName
    status: Literal["done", "skipped"]
    latency_ms: int
    model: str | None = None
    vram_peak_mb: int | None = None
    hit_count: int | None = None
    pool_size: int | None = None
    coarse_dim: int | None = None
    rescore_dim: int | None = None
    w1: float | None = None
    w2: float | None = None
    rerank_k: int | None = None


class RerankPreviewMeta(BaseModel):
    rerank_token_count: int
    rerank_ctx_limit: int
    rerank_doc_count: int
    rerank_k: int


class SearchProgress(BaseModel):
    workflow_log: list[WorkflowPhase] = Field(default_factory=list)
    active_phase: WorkflowPhaseName | None = None
    span_id: str | None = None


IngestPhaseName = Literal[
    "front_matter",
    "family_split",
    "parent_split",
    "child_split",
    "grandchild_split",
    "embed_family",
    "embed_parent",
    "embed_child",
    "embed_grandchild",
    "neo4j_upsert",
]


class IngestPhase(BaseModel):
    phase: IngestPhaseName
    status: Literal["done", "skipped"]
    latency_ms: int
    parent_count: int | None = None
    child_count: int | None = None
    grandchild_count: int | None = None
    family_count: int | None = None
    embedded_count: int | None = None


class IngestProgress(BaseModel):
    workflow_log: list[IngestPhase] = Field(default_factory=list)
    active_phase: IngestPhaseName | None = None
    relative_path: str | None = None


class RerankConfirmRequest(BaseModel):
    confirm: bool


class RerankConfirmResponse(BaseModel):
    status: SearchJobStatus
    rerank_job_id: str | None = None
    hits: list[SearchHit] | None = None
    fusion_meta: FusionMeta | None = None
    workflow_log: list[WorkflowPhase] | None = None
    span_id: str | None = None
    rerank_preview: RerankPreviewMeta | None = None


class SearchResponse(BaseModel):
    job_id: str | None = None
    span_id: str
    cached: bool = False
    status: SearchJobStatus | None = None
    hits: list[SearchHit] | None = None
    fusion_meta: FusionMeta | None = None
    workflow_log: list[WorkflowPhase] | None = None
    rerank_preview: RerankPreviewMeta | None = None
    rerank_job_id: str | None = None
