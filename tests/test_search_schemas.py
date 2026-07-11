from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.search_schemas import SearchRequest, WorkflowPhase


def test_workflow_phase_schema():
    phase = WorkflowPhase(
        phase="query_embed",
        status="done",
        latency_ms=42,
        model="jina-retrieval",
        vram_peak_mb=4000,
    )
    assert phase.phase == "query_embed"


def test_search_request_accepts_valid_weights():
    req = SearchRequest(query="test", w1=0.7, w2=0.3, coarse_dim=256)
    assert req.w1 == 0.7
    assert req.w2 == 0.3


def test_search_request_rejects_invalid_weight_sum():
    with pytest.raises(ValidationError):
        SearchRequest(query="test", w1=0.8, w2=0.3, coarse_dim=256)


def test_search_request_rejects_invalid_coarse_dim():
    with pytest.raises(ValidationError):
        SearchRequest(query="test", coarse_dim=128)


def test_search_request_accepts_scope_fields():
    req = SearchRequest(
        query="test",
        folder_ids=["f1", "f2"],
        created_after="2026-01-01",
        created_before="2026-12-31",
        indexed_only=False,
    )
    assert req.folder_ids == ["f1", "f2"]
    assert req.indexed_only is False


def test_search_request_rejects_inverted_date_range():
    with pytest.raises(ValidationError):
        SearchRequest(
            query="test",
            created_after="2026-12-31",
            created_before="2026-01-01",
        )
