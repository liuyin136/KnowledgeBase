from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.fusion import FusionHit


def test_grandchild_rerank_skips_when_tokens_high():
    from app.workers import tasks

    fused = [
        FusionHit(
            chunk_id="c1",
            final_score=1.0,
            display_score=0.9,
            vector_score=0.5,
            bm25_score=0.5,
        )
    ]
    pool = {"c1": {"id": "c1", "content": "child text"}}
    client = MagicMock()
    client.get_grandchildren_for_children.return_value = [
        {"id": "g1", "child_id": "c1", "content": "sentence one"},
    ]

    with patch.object(tasks.jina_runtime, "estimate_rerank_prompt_tokens", return_value=9000):
        out = tasks._apply_grandchild_rerank_if_fit("query", fused, pool, client)
    assert out[0].chunk_id == "c1"


def test_grandchild_rerank_max_pools_child_scores():
    from app.workers import tasks

    fused = [
        FusionHit(chunk_id="c1", final_score=1.0, display_score=0.9, vector_score=0.5, bm25_score=0.5),
        FusionHit(chunk_id="c2", final_score=0.8, display_score=0.7, vector_score=0.4, bm25_score=0.4),
    ]
    pool = {"c1": {}, "c2": {}}
    client = MagicMock()
    client.get_grandchildren_for_children.return_value = [
        {"id": "g1", "child_id": "c1", "content": "a"},
        {"id": "g2", "child_id": "c2", "content": "b"},
    ]

    rerank_result = MagicMock()
    rerank_result.index = 1
    rerank_result.relevance_score = 0.99

    with (
        patch.object(tasks.jina_runtime, "estimate_rerank_prompt_tokens", return_value=100),
        patch.object(tasks.jina_runtime, "load_reranker"),
        patch.object(tasks.jina_runtime, "release_reranker"),
        patch.object(tasks.jina_runtime, "rerank_documents", return_value=[rerank_result]),
    ):
        out = tasks._apply_grandchild_rerank_if_fit("query", fused, pool, client)
    assert out[0].chunk_id == "c2"
