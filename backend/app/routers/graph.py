"""Graph traversal search over saved memory subgraphs."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.graph_schemas import GraphSearchRequest, GraphSearchResponse
from app.services.neo4j_client import get_neo4j_client

router = APIRouter(prefix="/api/v1/graph", tags=["graph"])


@router.post("/search", response_model=GraphSearchResponse)
def graph_search(body: GraphSearchRequest) -> GraphSearchResponse:
    client = get_neo4j_client()
    try:
        if body.mode == "local":
            raw = client.graph_search_local(
                seed_entity_id=body.seed_entity_id or "",
                hops=body.hops,
                memory_key=body.memory_key,
            )
        else:
            raw = client.graph_search_global(
                query=body.query or "",
                top_communities=body.top_communities,
                memory_key=body.memory_key,
            )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return GraphSearchResponse.model_validate(raw)
