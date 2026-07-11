from __future__ import annotations

import numpy as np

from app.services.fusion import compute_ndcg, fuse_hybrid
from app.services.matryoshka import matryoshka_truncate


def test_matryoshka_truncate_renormalizes():
    vec = np.array([3.0, 4.0, 0.0, 0.0], dtype=np.float32)
    out = matryoshka_truncate(vec, 2)
    assert out.shape == (2,)
    assert abs(float(np.linalg.norm(out)) - 1.0) < 1e-5


def test_fuse_hybrid_prefers_high_bm25_when_vector_tied():
    ids = ["a", "b", "c"]
    vector_scores = {"a": 0.9, "b": 0.91, "c": 0.5}
    bm25_scores = {"a": 0.2, "b": 0.1, "c": 0.95}
    hits = fuse_hybrid(ids, vector_scores, bm25_scores, w1=0.3, w2=0.7)
    assert hits[0].chunk_id == "c"


def test_compute_ndcg_perfect_ranking():
    ranked = ["x", "y", "z"]
    ndcg = compute_ndcg({"x", "y"}, ranked, k=3)
    assert ndcg == 1.0


def test_fuse_hybrid_hand_computed_zscore_fixture():
    """Regression lock: w2=0.3 pulls ranking toward high BM25 item."""
    ids = ["a", "b", "c"]
    vector_scores = {"a": 0.8, "b": 0.6, "c": 0.4}
    bm25_scores = {"a": 0.1, "b": 0.5, "c": 0.9}
    hits = fuse_hybrid(ids, vector_scores, bm25_scores, w1=0.7, w2=0.3)
    by_id = {h.chunk_id: h for h in hits}
    assert hits[0].chunk_id == "a"
    assert hits[1].chunk_id == "b"
    assert hits[2].chunk_id == "c"
    assert all(0.0 <= by_id[cid].display_score <= 1.0 for cid in ids)
