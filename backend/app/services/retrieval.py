"""
services/retrieval.py — RetrievalModule (Hybrid Search).

STRICT MODULE BOUNDARY (Backend §2):
  • This module ONLY scores. It NEVER embeds, NEVER chunks, NEVER persists.
    The orchestrator embeds the query, passes the vector + raw query to
    `hybrid_search`, and `hybrid_search` returns scored results.
  • Persistence of :Memory nodes happens in the orchestrator (it owns
    transactions), not here.

Hybrid search pipeline (per Backend §7.4 + construction note #2):
  1. Vector search on :KnowledgeChunk (HNSW cosine) via Neo4jClient.
  2. OPTIONAL BM25 search on :KnowledgeChunk via Neo4j fulltext.
  3. Fusion — TWO modes (construction note #2):
       • Manual (`autoTuneWeights=false`):
           fused = alpha * vectorScore + beta * bm25Score
           beta = 1 - alpha  (using the request's hybridAlpha)
       • Adaptive (`autoTuneWeights=true`):
           Sweep alpha ∈ {0.1, 0.2, ..., 0.9}; for each, compute fused scores
           for all candidates; pick the alpha whose TOP-1 result has the
           highest fused similarity. Return `bestAlpha` in SearchMetadata.
     Alternative fusion (commented): RRF (Reciprocal Rank Fusion). The
     weighted fusion is primary for v1.2 per construction note #2.
  4. OPTIONAL cross-encoder reranker (BGE-reranker-base) on top-N results.

Both vector and BM25 scores are min-max normalized across the candidate set
before fusion so alpha/beta have a stable interpretation regardless of the
raw score scales.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from app.core.constants import ADAPTIVE_ALPHA_GRID, DEFAULT_HYBRID_ALPHA
from app.core.exceptions import RerankError
from app.core.logging import get_logger
from app.db.neo4j_client import Neo4jClient
from app.schemas.search import SearchConfig, SearchResult, SearchMetadata
from app.utils.timing import now_ms, timed_sync

logger = get_logger("rag.services.retrieval")


# ─── Internal candidate record ───────────────────────────────────────────────


@dataclass
class _Candidate:
    """Internal retrieval candidate (chunk + parent + raw scores)."""

    chunk_id: str
    parent_id: str
    experiment_id: str
    chunk_index: int
    text: str
    token_count: int
    chunk_method: str
    embedding_method: str
    parent_source_file: str
    parent_text: str
    section: Optional[str]
    chunking_time_ms: float
    embedding_time_ms: float
    vector_score: float = 0.0
    bm25_score: Optional[float] = None
    fused_score: float = 0.0
    reranker_score: Optional[float] = None
    final_score: float = 0.0
    alpha_used: float = DEFAULT_HYBRID_ALPHA
    beta_used: float = 1.0 - DEFAULT_HYBRID_ALPHA


# ─── RetrievalModule ─────────────────────────────────────────────────────────


class RetrievalModule:
    """Hybrid search scorer. Stateless w.r.t. persistence — owns scoring only."""

    def __init__(self, neo4j: Neo4jClient) -> None:
        self._neo4j = neo4j
        self._reranker = None
        self._reranker_lock = threading.Lock()
        self._reranker_loaded = False
        self._reranker_load_error: Optional[str] = None

    # ─── public API ─────────────────────────────────────────────────────────

    def hybrid_search(
        self,
        *,
        query_text: str,
        query_vector: List[float],
        config: SearchConfig,
        experiment_id: Optional[str] = None,
    ) -> Tuple[List[SearchResult], SearchMetadata]:
        """Run hybrid search. Returns (results, metadata).

        Pure scoring — does NOT persist :Memory nodes (the orchestrator does
        that after this returns).
        """
        t0 = now_ms()

        # 1. Vector search on :KnowledgeChunk
        vector_rows, vector_ms = timed_sync(
            lambda: self._neo4j.vector_search_chunks(
                query_vector=query_vector,
                top_k=config.topKVector,
                experiment_id=experiment_id,
            )
        )

        # Build candidate map keyed by chunk_id.
        candidates: Dict[str, _Candidate] = {}
        for row in vector_rows:
            chunk = row.get("chunk") or {}
            parent = row.get("parent") or {}
            cid = chunk.get("id")
            if not cid:
                continue
            candidates[cid] = _Candidate(
                chunk_id=cid,
                parent_id=parent.get("id", ""),
                experiment_id=row.get("experiment_id") or parent.get("experiment_id", ""),
                chunk_index=chunk.get("chunk_index", 0),
                text=chunk.get("text", ""),
                token_count=chunk.get("token_count", 0),
                chunk_method=chunk.get("chunk_method", ""),
                embedding_method=chunk.get("embedding_method", ""),
                parent_source_file=parent.get("source_file", ""),
                parent_text=parent.get("text", ""),
                section=chunk.get("section"),
                chunking_time_ms=chunk.get("chunking_time_ms", 0.0) or 0.0,
                embedding_time_ms=chunk.get("embedding_time_ms", 0.0) or 0.0,
                vector_score=float(row.get("vector_score", 0.0)),
            )

        # 2. OPTIONAL BM25 search (top_k = topKVector * 3 to widen the candidate pool)
        bm25_ms = 0.0
        if config.useBm25:
            bm25_rows, bm25_ms = timed_sync(
                lambda: self._neo4j.bm25_search_chunks(query_text, top_k=config.topKVector * 3)
            )
            for row in bm25_rows:
                chunk = row.get("chunk") or {}
                parent = row.get("parent") or {}
                cid = chunk.get("id")
                if not cid:
                    continue
                bm25 = float(row.get("bm25_score", 0.0))
                if cid in candidates:
                    candidates[cid].bm25_score = bm25
                else:
                    candidates[cid] = _Candidate(
                        chunk_id=cid,
                        parent_id=parent.get("id", ""),
                        experiment_id=row.get("experiment_id") or parent.get("experiment_id", ""),
                        chunk_index=chunk.get("chunk_index", 0),
                        text=chunk.get("text", ""),
                        token_count=chunk.get("token_count", 0),
                        chunk_method=chunk.get("chunk_method", ""),
                        embedding_method=chunk.get("embedding_method", ""),
                        parent_source_file=parent.get("source_file", ""),
                        parent_text=parent.get("text", ""),
                        section=chunk.get("section"),
                        chunking_time_ms=chunk.get("chunking_time_ms", 0.0) or 0.0,
                        embedding_time_ms=chunk.get("embedding_time_ms", 0.0) or 0.0,
                        vector_score=0.0,
                        bm25_score=bm25,
                    )

        candidate_list = list(candidates.values())
        candidates_before_rerank = len(candidate_list)

        # 3. Fusion (manual or adaptive — construction note #2)
        best_alpha: Optional[float] = None
        if config.autoTuneWeights:
            best_alpha = self._adaptive_fuse(candidate_list, use_bm25=config.useBm25)
            alpha_used = best_alpha
        else:
            alpha_used = config.hybridAlpha
        beta_used = 1.0 - alpha_used
        self._apply_fusion(candidate_list, alpha=alpha_used, use_bm25=config.useBm25)

        # Sort by fused score (desc) and take top_n_rerank for reranking (or topK).
        candidate_list.sort(key=lambda c: c.fused_score, reverse=True)
        top_n = config.topNRerank if config.useReranker and config.topNRerank > 0 else config.topKVector
        top_candidates = candidate_list[: max(top_n, 1)]

        # 4. OPTIONAL cross-encoder reranker
        rerank_ms = 0.0
        results_after_rerank = len(top_candidates)
        if config.useReranker and config.topNRerank > 0 and top_candidates:
            try:
                rerank_scores, rerank_ms = timed_sync(
                    lambda: self._rerank(query_text, [c.text for c in top_candidates])
                )
                for c, score in zip(top_candidates, rerank_scores):
                    c.reranker_score = float(score)
                # final = reranker if available, else fused
                for c in top_candidates:
                    c.final_score = c.reranker_score if c.reranker_score is not None else c.fused_score
                top_candidates.sort(key=lambda c: c.final_score, reverse=True)
                results_after_rerank = len(top_candidates)
            except RerankError as exc:
                logger.warning(
                    "retrieval.rerank_failed",
                    extra={"event": "retrieval.rerank_failed", "error": exc.message},
                )
                # Fall back to fused scores
                for c in top_candidates:
                    c.final_score = c.fused_score
        else:
            for c in top_candidates:
                c.final_score = c.fused_score

        # 5. Build SearchResult list (rank 1..N)
        results: List[SearchResult] = []
        for i, c in enumerate(top_candidates):
            results.append(
                SearchResult(
                    rank=i + 1,
                    chunkId=c.chunk_id,
                    parentId=c.parent_id,
                    experimentId=c.experiment_id,
                    chunkIndex=c.chunk_index,
                    text=c.text,
                    tokenCount=c.token_count,
                    chunkMethod=c.chunk_method,
                    embeddingMethod=c.embedding_method,
                    parentSourceFile=c.parent_source_file,
                    parentTextPreview=_preview(c.parent_text, 220),
                    vectorScore=round(c.vector_score, 6),
                    bm25Score=round(c.bm25_score, 6) if c.bm25_score is not None else None,
                    fusedScore=round(c.fused_score, 6),
                    rerankerScore=round(c.reranker_score, 6) if c.reranker_score is not None else None,
                    finalScore=round(c.final_score, 6),
                    alphaUsed=round(alpha_used, 4),
                    betaUsed=round(beta_used, 4),
                    section=c.section,
                    chunkingTimeMs=round(c.chunking_time_ms, 3),
                    embeddingTimeMs=round(c.embedding_time_ms, 3),
                )
            )

        total_ms = now_ms() - t0
        metadata = SearchMetadata(
            searchId="",  # filled by orchestrator
            experimentId=experiment_id,
            queryEmbeddingTimeMs=0.0,  # filled by orchestrator
            vectorSearchTimeMs=round(vector_ms, 3),
            bm25SearchTimeMs=round(bm25_ms, 3),
            rerankTimeMs=round(rerank_ms, 3),
            totalSearchTimeMs=round(total_ms, 3),
            config=config,
            bestAlpha=round(best_alpha, 4) if best_alpha is not None else None,
            candidatesBeforeRerank=candidates_before_rerank,
            resultsAfterRerank=results_after_rerank,
        )
        return results, metadata

    # ─── fusion (construction note #2) ──────────────────────────────────────

    def _adaptive_fuse(self, candidates: List[_Candidate], *, use_bm25: bool) -> float:
        """Construction note #2: sweep alpha ∈ {0.1..0.9}, pick the alpha whose
        TOP-1 result has the highest fused similarity. Returns the best alpha.

        Mutates each candidate's `alpha_used`/`beta_used` ONLY for the final
        chosen alpha (applied by `_apply_fusion` after we pick the winner).
        """
        if not candidates:
            return DEFAULT_HYBRID_ALPHA
        # Pre-normalize the score components ONCE so each alpha sweep is cheap.
        v_norm = _min_max_normalize([c.vector_score for c in candidates])
        b_norm = _min_max_normalize(
            [(c.bm25_score if c.bm25_score is not None else 0.0) for c in candidates]
        )

        best_alpha = ADAPTIVE_ALPHA_GRID[0]
        best_top1 = -1.0
        for alpha in ADAPTIVE_ALPHA_GRID:
            beta = 1.0 - alpha
            top1 = -1.0
            for i, c in enumerate(candidates):
                v = v_norm[i]
                b = b_norm[i] if use_bm25 and c.bm25_score is not None else 0.0
                fused = alpha * v + beta * b if use_bm25 else v
                if fused > top1:
                    top1 = fused
            if top1 > best_top1:
                best_top1 = top1
                best_alpha = alpha
        return best_alpha

    def _apply_fusion(self, candidates: List[_Candidate], *, alpha: float, use_bm25: bool) -> None:
        """Apply manual/adaptive weighted fusion to each candidate.

        score = alpha * vectorScore + beta * bm25Score   (beta = 1 - alpha)
        When BM25 is disabled, fused = vectorScore (min-max normalized).
        """
        if not candidates:
            return
        v_norm = _min_max_normalize([c.vector_score for c in candidates])
        b_norm = _min_max_normalize(
            [(c.bm25_score if c.bm25_score is not None else 0.0) for c in candidates]
        )
        beta = 1.0 - alpha
        for i, c in enumerate(candidates):
            v = v_norm[i]
            b = b_norm[i] if use_bm25 and c.bm25_score is not None else 0.0
            c.fused_score = alpha * v + beta * b if use_bm25 else v
            c.alpha_used = alpha
            c.beta_used = beta

    # ─── RRF (alternative fusion — commented per construction note #2) ──────

    def _rrf_fuse(
        self,
        vector_ranked: List[str],  # chunk_ids in vector rank order
        bm25_ranked: List[str],    # chunk_ids in bm25 rank order
        k: int = 60,
    ) -> Dict[str, float]:
        """Reciprocal Rank Fusion (alternative to weighted fusion).

        NOTE: weighted fusion (alpha*vector + beta*bm25) is the PRIMARY fusion
        for v1.2 per construction note #2. RRF is provided here as a documented
        alternative for future experimentation — not invoked by hybrid_search
        in v1.2.
        """
        scores: Dict[str, float] = {}
        for rank, cid in enumerate(vector_ranked):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
        for rank, cid in enumerate(bm25_ranked):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
        return scores

    # ─── Cross-encoder reranker (optional) ──────────────────────────────────

    def _ensure_reranker(self) -> bool:
        """Lazy-load BGE-reranker-base. Returns True if available."""
        from app.core.config import settings

        if not settings.enable_reranker:
            return False
        with self._reranker_lock:
            if self._reranker_loaded:
                return self._reranker is not None
            self._reranker_loaded = True
            try:
                import os

                from sentence_transformers import CrossEncoder  # local import

                local_path = os.path.join(settings.model_path, settings.reranker_model_name)
                model_src = local_path if os.path.isdir(local_path) else settings.bge_reranker_repo
                self._reranker = CrossEncoder(model_src, device=settings.device, max_length=512)
                logger.info(
                    "reranker.load.ok",
                    extra={"event": "reranker.load.ok", "model_src": model_src, "device": settings.device},
                )
                return True
            except Exception as exc:
                self._reranker_load_error = str(exc)
                logger.warning(
                    "reranker.load.failed",
                    extra={"event": "reranker.load.failed", "error": str(exc)},
                )
                return False

    def _rerank(self, query: str, passages: List[str]) -> Tuple[List[float], float]:
        """Score (query, passage) pairs with the cross-encoder. Returns (scores, ms)."""
        if not passages:
            return [], 0.0
        if not self._ensure_reranker():
            # No reranker available — return neutral 0.5 scores (so the fused score is used).
            return [0.5] * len(passages), 0.0
        t0 = now_ms()
        try:
            pairs = [(query, p) for p in passages]
            scores = self._reranker.predict(pairs, show_progress_bar=False)
            # CrossEncoder returns a numpy array (float32 already on CPU). Coerce to float list.
            try:
                return [float(s) for s in scores], now_ms() - t0
            except Exception:
                return [float(s) for s in scores.tolist()], now_ms() - t0
        except Exception as exc:
            raise RerankError(
                f"Reranker predict failed: {exc}",
                stage="rerank",
            ) from exc


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _min_max_normalize(values: List[float]) -> List[float]:
    """Min-max normalize to [0, 1]. All-equal → all 1.0 (avoids div-by-zero)."""
    if not values:
        return []
    lo = min(values)
    hi = max(values)
    if hi - lo < 1e-9:
        return [1.0 if v > 0 else 0.0 for v in values]
    rng = hi - lo
    return [(v - lo) / rng for v in values]


def _preview(text: str, max_len: int = 220) -> str:
    from app.utils.tokenization import preview as _p

    return _p(text, max_len)
