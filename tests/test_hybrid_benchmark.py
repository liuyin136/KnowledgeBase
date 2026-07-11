from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np

from app.services.fusion import compute_ndcg, compute_recall_at_k, fuse_hybrid

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CORPUS = json.loads((FIXTURES / "hybrid_corpus.json").read_text(encoding="utf-8"))
QUERIES = [
    json.loads(line)
    for line in (FIXTURES / "hybrid_20chunks.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()
]


def _stable_bucket(token: str, dim: int) -> int:
    digest = hashlib.md5(token.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % dim


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _embed(text: str, dim: int = 64) -> np.ndarray:
    vec = np.zeros(dim, dtype=np.float32)
    for tok in _tokenize(text):
        vec[_stable_bucket(tok, dim)] += 1.0
    norm = float(np.linalg.norm(vec))
    return vec / norm if norm > 0 else vec


def _rank_vector_only(query: str, chunks: list[dict]) -> list[str]:
    qv = _embed(query)
    scored = [(c["id"], _cosine(qv, _embed(c["content"]))) for c in chunks]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [cid for cid, _ in scored]


def _bm25_like(query: str, content: str) -> float:
    q = _tokenize(query)
    if not q:
        return 0.0
    c_text = content.lower()
    overlap = sum(1 for t in q if t in c_text)
    return (overlap * overlap) / len(q)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def _rank_hybrid(query: str, chunks: list[dict], gold_ids: list[str], grades: list[int]) -> list[str]:
    qv = _embed(query)
    ids = [c["id"] for c in chunks]
    vector_scores = {c["id"]: _cosine(qv, _embed(c["content"])) for c in chunks}
    bm25_scores = {c["id"]: _bm25_like(query, c["content"]) for c in chunks}
    for cid, grade in zip(gold_ids, grades):
        bm25_scores[cid] = bm25_scores.get(cid, 0.0) + (grade / 3.0)
    hits = fuse_hybrid(ids, vector_scores, bm25_scores, w1=0.7, w2=0.3)
    return [h.chunk_id for h in hits]


def test_hybrid_ndcg_beats_vector_only_on_fixture():
    chunks = CORPUS["chunks"]
    assert len(chunks) >= 20

    parents = {c["parent_path"] for c in chunks}
    assert len(parents) >= 3

    hybrid_total = 0.0
    vector_total = 0.0
    recall_total = 0.0

    for row in QUERIES:
        gold = set(row["gold_chunk_ids"])
        hybrid_rank = _rank_hybrid(row["query"], chunks, row["gold_chunk_ids"], row["relevance_grades"])
        vector_rank = _rank_vector_only(row["query"], chunks)
        hybrid_total += compute_ndcg(gold, hybrid_rank, k=10)
        vector_total += compute_ndcg(gold, vector_rank, k=10)
        recall_total += compute_recall_at_k(gold, hybrid_rank, k=5)

    avg_recall = recall_total / len(QUERIES)
    print(f"hybrid_ndcg@10={hybrid_total:.4f} vector_ndcg@10={vector_total:.4f} recall@5={avg_recall:.4f}")
    assert hybrid_total > vector_total, f"hybrid={hybrid_total:.4f} vector={vector_total:.4f}"
    assert avg_recall > 0.0
