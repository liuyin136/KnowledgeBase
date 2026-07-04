/**
 * BM25 scoring (in-memory) — replaces Neo4j fulltext index for v1.
 * Standard Okapi BM25 over tokenized chunk texts. Research-scale corpus so
 * in-memory is fine; provides the BM25 axis of hybrid search.
 */

import { minMaxNormalize } from "./vectors";

const STOPWORDS = new Set([
  "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "be", "been",
  "being", "have", "has", "had", "do", "does", "did", "will", "would", "could",
  "should", "may", "might", "must", "shall", "can", "need", "of", "to", "in",
  "for", "on", "with", "as", "by", "at", "from", "up", "about", "into", "through",
  "during", "before", "after", "above", "below", "between", "this", "that", "these",
  "those", "i", "you", "he", "she", "it", "we", "they", "what", "which", "who",
]);

/** Tokenize: lowercase, split on non-word (keep CJK), strip stopwords. */
export function tokenize(text: string): string[] {
  if (!text) return [];
  // Split CJK chars individually, latin words by boundary.
  const raw = text
    .toLowerCase()
    .replace(/[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]/g, " $& ")
    .split(/[^a-z0-9\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]+/i)
    .filter(Boolean);
  return raw.filter((t) => t.length > 1 || /[\u4e00-\u9fff]/.test(t)).filter((t) => !STOPWORDS.has(t));
}

export interface BM25Index {
  docs: { id: string; tokens: string[]; length: number }[];
  avgDocLength: number;
  df: Map<string, number>; // document frequency per term
  N: number;
}

/** Build an in-memory BM25 index over a corpus of {id, text}. */
export function buildBM25Index(corpus: { id: string; text: string }[]): BM25Index {
  const docs = corpus.map((d) => {
    const tokens = tokenize(d.text);
    return { id: d.id, tokens, length: tokens.length };
  });
  const df = new Map<string, number>();
  for (const d of docs) {
    const seen = new Set(d.tokens);
    for (const t of seen) df.set(t, (df.get(t) ?? 0) + 1);
  }
  const totalLen = docs.reduce((s, d) => s + d.length, 0);
  const avgDocLength = docs.length ? totalLen / docs.length : 0;
  return { docs, avgDocLength, df, N: docs.length };
}

/**
 * Score a single document against query terms using Okapi BM25.
 * k1=1.5, b=0.75 (standard defaults).
 */
export function bm25Score(
  index: BM25Index,
  docTokens: string[],
  docLength: number,
  queryTerms: string[],
  k1 = 1.5,
  b = 0.75,
): number {
  if (queryTerms.length === 0 || index.N === 0) return 0;
  let score = 0;
  const tf = new Map<string, number>();
  for (const t of docTokens) tf.set(t, (tf.get(t) ?? 0) + 1);

  for (const term of queryTerms) {
    const f = tf.get(term) ?? 0;
    if (f === 0) continue;
    const n = index.df.get(term) ?? 0;
    // IDF (Okapi variant, with +1 to keep non-negative)
    const idf = Math.log(1 + (index.N - n + 0.5) / (n + 0.5));
    const denom = f + k1 * (1 - b + b * (docLength / (index.avgDocLength || 1)));
    score += (idf * (f * (k1 + 1))) / denom;
  }
  return score;
}

/** Search the index; return raw scores map (id -> bm25 score). */
export function bm25SearchRaw(index: BM25Index, query: string): Map<string, number> {
  const queryTerms = tokenize(query);
  const scores = new Map<string, number>();
  for (const d of index.docs) {
    const s = bm25Score(index, d.tokens, d.length, queryTerms);
    if (s > 0) scores.set(d.id, s);
  }
  return scores;
}

/** Search + normalize to 0..1 + return ranked id list (best first). */
export function bm25SearchRanked(index: BM25Index, query: string): { id: string; score: number }[] {
  const raw = bm25SearchRaw(index, query);
  const entries = [...raw.entries()].map(([id, score]) => ({ id, score }));
  if (entries.length === 0) return [];
  const scores = entries.map((e) => e.score);
  const norm = minMaxNormalize(scores);
  entries.forEach((e, i) => (e.score = norm[i]));
  return entries.sort((a, b) => b.score - a.score);
}
