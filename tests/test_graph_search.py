"""Graph search contract tests (schemas only — no FastAPI import in worker)."""
from __future__ import annotations

import pytest

from app.models.graph_schemas import GraphSearchRequest, GraphSearchResponse


def test_graph_search_local_requires_seed():
    with pytest.raises(ValueError):
        GraphSearchRequest(mode="local")


def test_graph_search_global_requires_query():
    with pytest.raises(ValueError):
        GraphSearchRequest(mode="global")


def test_graph_search_response_roundtrip():
    raw = {
        "paths": [{"entities": [{"entity_id": "e1"}], "relations": [], "claims": []}],
        "community_summaries": [{"community_id": "c0", "level": 0, "text": "sum"}],
        "sources": [{"grandchild_id": "g1", "source_file": "a.md", "fusion_score": 0.0}],
    }
    resp = GraphSearchResponse.model_validate(raw)
    assert resp.paths[0].entities[0]["entity_id"] == "e1"
