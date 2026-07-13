"""REST schemas for graph search API."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class GraphSearchRequest(BaseModel):
    mode: Literal["local", "global"]
    seed_entity_id: str | None = None
    hops: int = Field(default=2, ge=1, le=5)
    query: str | None = None
    top_communities: int = Field(default=3, ge=1, le=10)
    memory_key: str | None = None

    @model_validator(mode="after")
    def _validate_mode_fields(self) -> "GraphSearchRequest":
        if self.mode == "local" and not self.seed_entity_id:
            raise ValueError("seed_entity_id required for local mode")
        if self.mode == "global" and not (self.query and self.query.strip()):
            raise ValueError("query required for global mode")
        return self


class GraphPath(BaseModel):
    entities: list[dict[str, Any]] = Field(default_factory=list)
    relations: list[dict[str, Any]] = Field(default_factory=list)
    claims: list[dict[str, Any]] = Field(default_factory=list)
    community_id: str | None = None


class GraphSource(BaseModel):
    grandchild_id: str | None = None
    source_file: str | None = None
    fusion_score: float = 0.0


class CommunitySummaryHit(BaseModel):
    community_id: str
    level: int = 0
    text: str = ""


class GraphSearchResponse(BaseModel):
    paths: list[GraphPath] = Field(default_factory=list)
    community_summaries: list[CommunitySummaryHit] = Field(default_factory=list)
    sources: list[GraphSource] = Field(default_factory=list)
