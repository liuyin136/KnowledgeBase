from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

EPS = 1e-8


@dataclass
class FusionHit:
    chunk_id: str
    final_score: float
    display_score: float
    vector_score: float
    bm25_score: float


def z_score(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return values
    mu = float(np.mean(values))
    sigma = float(np.std(values))
    if sigma < EPS or values.size <= 1:
        return values - mu
    return (values - mu) / (sigma + EPS)


def minmax_scale(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return values
    lo = float(np.min(values))
    hi = float(np.max(values))
    if hi - lo < EPS:
        return np.zeros_like(values)
    return (values - lo) / (hi - lo + EPS)


def fuse_hybrid(
    chunk_ids: list[str],
    vector_scores: dict[str, float],
    bm25_scores: dict[str, float],
    *,
    w1: float = 0.7,
    w2: float = 0.3,
    use_minmax_fallback: bool = False,
) -> list[FusionHit]:
    if not chunk_ids:
        return []

    v_arr = np.array([vector_scores.get(cid, 0.0) for cid in chunk_ids], dtype=np.float32)
    b_arr = np.array([bm25_scores.get(cid, 0.0) for cid in chunk_ids], dtype=np.float32)

    if use_minmax_fallback:
        z_v = minmax_scale(v_arr)
        z_b = minmax_scale(b_arr)
    else:
        z_v = z_score(v_arr)
        z_b = z_score(b_arr)

    finals = w1 * z_v + w2 * z_b
    display = minmax_scale(finals)

    hits = [
        FusionHit(
            chunk_id=cid,
            final_score=float(finals[i]),
            display_score=float(display[i]),
            vector_score=float(v_arr[i]),
            bm25_score=float(b_arr[i]),
        )
        for i, cid in enumerate(chunk_ids)
    ]
    hits.sort(key=lambda h: h.final_score, reverse=True)
    return hits


def compute_recall_at_k(relevant: set[str], ranked_ids: list[str], k: int) -> float:
    if not relevant:
        return 0.0
    top = ranked_ids[:k]
    hits = sum(1 for cid in top if cid in relevant)
    return float(hits) / len(relevant)


def compute_ndcg(relevant: set[str], ranked_ids: list[str], k: int) -> float:
    top = ranked_ids[:k]
    relevances = [1.0 if cid in relevant else 0.0 for cid in top]
    dcg = sum(r / np.log2(i + 2) for i, r in enumerate(relevances))
    ideal_count = min(len(relevant), k)
    ideal = [1.0] * ideal_count + [0.0] * (k - ideal_count)
    idcg = sum(r / np.log2(i + 2) for i, r in enumerate(ideal))
    return float(dcg / idcg) if idcg > 0 else 0.0
