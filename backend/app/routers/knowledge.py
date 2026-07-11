"""Knowledge context stub for Phase 2+ chat agent handoff."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


class KnowledgeContextRequest(BaseModel):
    query: str = Field(min_length=1)
    parent_ids: list[str] = Field(default_factory=list)
    parent_contents: list[str] = Field(default_factory=list)


class KnowledgeContextResponse(BaseModel):
    query: str
    parent_ids: list[str]
    assembled_markdown: str
    status: str = "stub"


@router.post("/context", response_model=KnowledgeContextResponse)
def knowledge_context(body: KnowledgeContextRequest) -> KnowledgeContextResponse:
    """Return assembled parent markdown for a future LLM worker (no model call in 1.6)."""
    parts = [c.strip() for c in body.parent_contents if c.strip()]
    assembled = "\n\n---\n\n".join(parts)
    return KnowledgeContextResponse(
        query=body.query,
        parent_ids=body.parent_ids,
        assembled_markdown=assembled,
    )
