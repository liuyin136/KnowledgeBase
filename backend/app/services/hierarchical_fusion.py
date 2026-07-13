"""Phase 1.62 hierarchical score aggregation across Family→Parent→Child→Grandchild."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.core.constants import TIER_WEIGHTS
from app.services.fusion import FusionHit, fuse_hybrid, minmax_scale, z_score


@dataclass
class HierarchicalHit:
    grandchild_id: str
    child_id: str
    parent_id: str
    family_id: str
    vector_score: float
    final_score: float
    display_score: float
    bm25_score: float = 0.0
    tier_vector_scores: dict[str, float] = field(default_factory=dict)
    content: str = ""
    parent_content: str = ""
    header_path: str = ""
    source_file: str = ""
    child_index: int = 0


def fuse_tier_pool(
    ids: list[str],
    vector_scores: dict[str, float],
    bm25_scores: dict[str, float],
    *,
    w1: float,
    w2: float,
    use_minmax_fallback: bool = False,
    top_k: int,
) -> list[FusionHit]:
    hits = fuse_hybrid(
        ids,
        vector_scores,
        bm25_scores,
        w1=w1,
        w2=w2,
        use_minmax_fallback=use_minmax_fallback,
    )
    return hits[:top_k]


def aggregate_hierarchical_scores(
    paths: list[dict[str, Any]],
    *,
    tier_weights: dict[str, float] | None = None,
) -> list[HierarchicalHit]:
    """
    paths items must include:
      grandchild_id, child_id, parent_id, family_id,
      family_vector, parent_vector, child_vector, grandchild_vector,
      optional bm25_score, content, parent_content, header_path, source_file, child_index
    """
    if not paths:
        return []

    weights = tier_weights or TIER_WEIGHTS
    family_vals = np.array([float(p.get("family_vector") or 0.0) for p in paths], dtype=np.float32)
    parent_vals = np.array([float(p.get("parent_vector") or 0.0) for p in paths], dtype=np.float32)
    child_vals = np.array([float(p.get("child_vector") or 0.0) for p in paths], dtype=np.float32)
    gc_vals = np.array([float(p.get("grandchild_vector") or 0.0) for p in paths], dtype=np.float32)

    z_f = z_score(family_vals)
    z_p = z_score(parent_vals)
    z_c = z_score(child_vals)
    z_g = z_score(gc_vals)

    finals = (
        float(weights.get("family", 0.35)) * z_f
        + float(weights.get("parent", 0.25)) * z_p
        + float(weights.get("child", 0.20)) * z_c
        + float(weights.get("grandchild", 0.12)) * z_g
    )
    display = minmax_scale(finals)

    hits: list[HierarchicalHit] = []
    for i, p in enumerate(paths):
        hits.append(
            HierarchicalHit(
                grandchild_id=str(p["grandchild_id"]),
                child_id=str(p["child_id"]),
                parent_id=str(p["parent_id"]),
                family_id=str(p["family_id"]),
                vector_score=float(p.get("grandchild_vector") or 0.0),
                final_score=float(finals[i]),
                display_score=float(display[i]),
                bm25_score=float(p.get("bm25_score") or 0.0),
                tier_vector_scores={
                    "family": float(p.get("family_vector") or 0.0),
                    "parent": float(p.get("parent_vector") or 0.0),
                    "child": float(p.get("child_vector") or 0.0),
                    "grandchild": float(p.get("grandchild_vector") or 0.0),
                },
                content=str(p.get("content") or ""),
                parent_content=str(p.get("parent_content") or ""),
                header_path=str(p.get("header_path") or ""),
                source_file=str(p.get("source_file") or ""),
                child_index=int(p.get("child_index") or 0),
            )
        )
    hits.sort(key=lambda h: h.final_score, reverse=True)
    return hits


def apply_rerank_weight(
    hits: list[HierarchicalHit],
    rerank_by_id: dict[str, float],
    *,
    rerank_weight: float | None = None,
) -> list[HierarchicalHit]:
    """Blend hierarchical final with z-scored rerank into display ordering."""
    if not hits:
        return hits
    w5 = float(rerank_weight if rerank_weight is not None else TIER_WEIGHTS.get("rerank", 0.08))
    w_base = 1.0 - w5
    r_vals = np.array(
        [float(rerank_by_id.get(h.grandchild_id, 0.0)) for h in hits],
        dtype=np.float32,
    )
    z_r = z_score(r_vals)
    base = np.array([h.final_score for h in hits], dtype=np.float32)
    combined = w_base * base + w5 * z_r
    display = minmax_scale(combined)
    for i, h in enumerate(hits):
        h.final_score = float(combined[i])
        h.display_score = float(display[i])
    hits.sort(key=lambda h: h.final_score, reverse=True)
    return hits
