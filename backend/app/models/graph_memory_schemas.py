"""Pydantic models for Phase 2 GraphRAG + memory extraction."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ExtractEntity(BaseModel):
    entity_id: str
    name: str
    type: str = "concept"


class ExtractRelation(BaseModel):
    source_id: str
    target_id: str
    type: str = "related_to"
    weight: float = 1.0


class ExtractClaim(BaseModel):
    claim_id: str
    text: str
    entity_id: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    grandchild_id: str | None = None


class GraphExtractResult(BaseModel):
    summary: str = ""
    entities: list[ExtractEntity] = Field(default_factory=list)
    relations: list[ExtractRelation] = Field(default_factory=list)
    claims: list[ExtractClaim] = Field(default_factory=list)


class MemoryGraphStats(BaseModel):
    memory_id: str
    memory_key: str
    version: int = 1
    entities_created: int = 0
    relations_created: int = 0
    claims_created: int = 0
    communities_created: int = 0
    summaries_created: int = 0


class CommunityPartition(BaseModel):
    community_id: str
    level: int = 0
    entity_ids: list[str] = Field(default_factory=list)


class CommunitySummaryRecord(BaseModel):
    summary_id: str
    community_id: str
    level: int = 0
    text: str = ""
