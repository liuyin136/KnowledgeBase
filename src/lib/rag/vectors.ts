/**
 * Vector math + retrieval fusion utilities.
 * Replaces Neo4j HNSW vector index with in-memory cosine similarity over
 * stored number[] vectors (v1 research-scale corpus; adequate for the
 * experimentation platform's tinkering goal).
 *
 * Mirrors db/vector_index.py helper logic from backend-directory-structure spec.
 */

import type { SearchResult } from "./types";

/** Cosine similarity between two equal-length vectors. Returns -1..1. */
export function cosine(a: number[], b: number[]): number {
  if (a.length !== b.length || a.length === 0) return 0;
  let dot = 0;
  let na = 0;
  let nb = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    na += a[i] * a[i];
    nb += b[i] * b[i];
  }
  if (na === 0 || nb === 0) return 0;
  return dot / (Math.sqrt(na) * Math.sqrt(nb));
}

/** Max-pool child scores up to parent level (Slice 4 spec §7.4). */
export function maxPool<T extends { parentId: string; vectorScore: number }>(
  candidates: T[],
): Map<string, number> {
  const pool = new Map<string, number>();
  for (const c of candidates) {
    const prev = pool.get(c.parentId) ?? -Infinity;
    if (c.vectorScore > prev) pool.set(c.parentId, c.vectorScore);
  }
  return pool;
}

/**
 * Reciprocal Rank Fusion (Slice 5). Combines vector + BM25 ranked lists.
 * Standard RRF: score(d) = Σ 1 / (k + rank_i(d)), k=60 typical.
 */
export function reciprocalRankFusion(
  vectorRanked: string[],
  bm25Ranked: string[],
  k = 60,
): Map<string, number> {
  const fused = new Map<string, number>();
  vectorRanked.forEach((id, rank) => {
    fused.set(id, (fused.get(id) ?? 0) + 1 / (k + rank + 1));
  });
  bm25Ranked.forEach((id, rank) => {
    fused.set(id, (fused.get(id) ?? 0) + 1 / (k + rank + 1));
  });
  return fused;
}

/**
 * Weighted fusion: score = alpha * vectorScore + beta * bm25Score
 * where alpha + beta = 1. Used for adaptive sweep (construction note #2).
 * Both scores must be normalized to 0..1 first.
 */
export function weightedFuse(
  vectorScore: number,
  bm25Score: number | null,
  alpha: number,
): number {
  const beta = 1 - alpha;
  if (bm25Score === null) return vectorScore;
  return alpha * vectorScore + beta * bm25Score;
}

/** Min-max normalize an array of numbers to 0..1. Returns [0..1] array. */
export function minMaxNormalize(values: number[]): number[] {
  if (values.length === 0) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (max === min) return values.map(() => 1);
  return values.map((v) => (v - min) / (max - min));
}

/** Sort candidates by a score selector, return top N. */
export function topN<T>(candidates: T[], scoreOf: (c: T) => number, n: number): T[] {
  return [...candidates].sort((a, b) => scoreOf(b) - scoreOf(a)).slice(0, n);
}

/** Re-rank in place by a new score selector and reassign rank field. */
export function reassignRanks(results: SearchResult[]): SearchResult[] {
  return results.map((r, i) => ({ ...r, rank: i + 1 }));
}
