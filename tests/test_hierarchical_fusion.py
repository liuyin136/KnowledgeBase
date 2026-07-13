"""Unit tests for hierarchical fusion aggregation (no GPU)."""
from __future__ import annotations

from app.services.hierarchical_fusion import (
    aggregate_hierarchical_scores,
    apply_rerank_weight,
    fuse_tier_pool,
)


def test_fuse_tier_pool_respects_top_k():
    ids = ["a", "b", "c"]
    hits = fuse_tier_pool(
        ids,
        {"a": 0.9, "b": 0.5, "c": 0.1},
        {"a": 0.1, "b": 0.5, "c": 0.9},
        w1=0.7,
        w2=0.3,
        top_k=2,
    )
    assert len(hits) == 2


def test_aggregate_hierarchical_scores_orders_by_final():
    paths = [
        {
            "grandchild_id": "g1",
            "child_id": "c1",
            "parent_id": "p1",
            "family_id": "f1",
            "family_vector": 0.1,
            "parent_vector": 0.1,
            "child_vector": 0.1,
            "grandchild_vector": 0.1,
        },
        {
            "grandchild_id": "g2",
            "child_id": "c2",
            "parent_id": "p2",
            "family_id": "f2",
            "family_vector": 0.9,
            "parent_vector": 0.9,
            "child_vector": 0.9,
            "grandchild_vector": 0.9,
        },
    ]
    hits = aggregate_hierarchical_scores(paths)
    assert hits[0].grandchild_id == "g2"
    assert hits[0].vector_score == 0.9
    assert hits[0].display_score >= hits[1].display_score


def test_apply_rerank_weight_changes_order():
    paths = [
        {
            "grandchild_id": "g1",
            "child_id": "c1",
            "parent_id": "p1",
            "family_id": "f1",
            "family_vector": 0.9,
            "parent_vector": 0.9,
            "child_vector": 0.9,
            "grandchild_vector": 0.9,
        },
        {
            "grandchild_id": "g2",
            "child_id": "c2",
            "parent_id": "p2",
            "family_id": "f2",
            "family_vector": 0.2,
            "parent_vector": 0.2,
            "child_vector": 0.2,
            "grandchild_vector": 0.2,
        },
    ]
    hits = aggregate_hierarchical_scores(paths)
    assert hits[0].grandchild_id == "g1"
    reordered = apply_rerank_weight(hits, {"g1": 0.1, "g2": 0.99}, rerank_weight=0.9)
    assert reordered[0].grandchild_id == "g2"
