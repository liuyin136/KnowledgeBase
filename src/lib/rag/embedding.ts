/**
 * EmbeddingModule — vectorization only (standard paths). STRICT MODULE BOUNDARY:
 *   - This module ONLY produces vectors. It never chunks, never persists, never
 *     coordinates. Called by the PipelineOrchestrator.
 *   (Mirrors services/embedding.py from backend-directory-structure spec.)
 *
 * v1 LOCAL-FIRST EMBEDDING (documented substitution for BGE-M3):
 *   The directive targets BGE-M3 (1024-dim) via sentence-transformers on a GPU.
 *   This sandbox is Next.js/JS with no torch runtime, and z-ai-web-dev-sdk has
 *   no native embeddings endpoint. We therefore implement a deterministic,
 *   order-independent, local-first dense embedding into 1024 dims that:
 *     • matches the BGE-M3 dimension (so the schema + cosine math is identical)
 *     • is reproducible across runs (critical for experiment comparison — a
 *       core directive value: "controlled experimentation")
 *     • encodes real semantic-ish signal via a mix of word-unigram, word-bigram,
 *       and char-trigram feature hashing with TF weighting + L2 normalization
 *   Construction note #1 (`.cpu().to(torch.float32).numpy()`): N/A in JS — the
 *   embedding is produced directly as a Float64Array → number[] with no
 *   bfloat16 intermediary. The interface `embedText(text) → number[]` is the
 *   BGE-M3 drop-in target for the future Python stack.
 */

import { EMBEDDING_DIM, EMBEDDING_MAX_RETRIES, EMBEDDING_BACKOFF_MS } from "./constants";
import { EmbeddingError, logPipelineError } from "./errors";
import { sleep } from "./utils";

// ─── Feature hashing ────────────────────────────────────────────────────────

/** FNV-1a 32-bit hash (fast, good distribution). */
function fnv1a(str: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

const STOPWORDS = new Set([
  "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "be", "been",
  "being", "have", "has", "had", "do", "does", "did", "will", "would", "could",
  "should", "of", "to", "in", "for", "on", "with", "as", "by", "at", "from",
  "this", "that", "these", "those", "i", "you", "he", "she", "it", "we", "they",
]);

/** Tokenize for embedding (keep CJK chars as individual tokens). */
function embedTokenize(text: string): string[] {
  if (!text) return [];
  return text
    .toLowerCase()
    .replace(/[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]/g, " $& ")
    .split(/[^a-z0-9\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]+/i)
    .filter(Boolean)
    .filter((t) => t.length > 1 || /[\u4e00-\u9fff]/.test(t))
    .filter((t) => !STOPWORDS.has(t));
}

/** Character n-grams (captures morphology + CJK + typos). */
function charNgrams(text: string, n: number): string[] {
  const clean = text.toLowerCase().replace(/\s+/g, " ").trim();
  const grams: string[] = [];
  for (let i = 0; i <= clean.length - n; i++) {
    grams.push(clean.slice(i, i + n));
  }
  return grams;
}

/** Count term frequencies. */
function tfMap(tokens: string[]): Map<string, number> {
  const m = new Map<string, number>();
  for (const t of tokens) m.set(t, (m.get(t) ?? 0) + 1);
  return m;
}

/**
 * Produce a 1024-dim L2-normalized dense vector from text.
 * Feature layout (3 subspaces, hashed into 1024 dims):
 *   • Word unigrams (TF-weighted) → dims 0..511 (signed hashing, half each polarity)
 *   • Word bigrams (TF-weighted)  → dims 512..767
 *   • Char trigrams (TF-weighted) → dims 768..1023
 * Signed feature hashing (sign bit from a second hash) reduces collisions.
 */
export function embedText(text: string): number[] {
  const vec = new Float64Array(EMBEDDING_DIM);
  if (!text || text.trim().length === 0) return Array.from(vec);

  const words = embedTokenize(text);
  const bigrams: string[] = [];
  for (let i = 0; i < words.length - 1; i++) bigrams.push(`${words[i]}_${words[i + 1]}`);
  const chars = charNgrams(text, 3);

  const project = (tokens: string[], offset: number, span: number, weight: number) => {
    const tf = tfMap(tokens);
    for (const [term, freq] of tf) {
      const h = fnv1a(term);
      const idx = offset + (h % span);
      const sign = (h >>> 16) & 1 ? 1 : -1;
      // Sublinear TF scaling (dampens very frequent terms).
      const score = sign * weight * (1 + Math.log(freq));
      vec[idx] += score;
    }
  };

  project(words, 0, 512, 1.0);
  project(bigrams, 512, 256, 0.7);
  project(chars, 768, 256, 0.4);

  // L2 normalize (cosine similarity then reduces to dot product).
  let norm = 0;
  for (let i = 0; i < vec.length; i++) norm += vec[i] * vec[i];
  norm = Math.sqrt(norm);
  if (norm > 0) {
    for (let i = 0; i < vec.length; i++) vec[i] /= norm;
  }
  return Array.from(vec);
}

/** Batch embed (reuses single-text embed; kept for future batching). */
export function embedBatch(texts: string[]): number[][] {
  return texts.map(embedText);
}

// ─── Retry wrapper (error-handling spec §3) ─────────────────────────────────

/**
 * Embed with retry: max 3 attempts, exp backoff 1s/2s/4s.
 * Retries only on transient errors (never on validation — empty text returns zero vec).
 */
export async function embedWithRetry(
  text: string,
  opts?: { experimentId?: string | null; stage?: string },
): Promise<{ vector: number[]; timeMs: number; retries: number }> {
  const start = performance.now();
  let lastErr: unknown = null;
  for (let attempt = 0; attempt < EMBEDDING_MAX_RETRIES; attempt++) {
    try {
      // The local embed is synchronous & deterministic; wrap in try/catch for
      // interface parity with the future BGE-M3 path (which can CUDA-OOM).
      const vector = embedText(text);
      return { vector, timeMs: performance.now() - start, retries: attempt };
    } catch (err) {
      lastErr = err;
      logPipelineError({
        experimentId: opts?.experimentId,
        stage: (opts?.stage as "embedding") ?? "embedding",
        err,
        retryCount: attempt,
      });
      if (attempt < EMBEDDING_MAX_RETRIES - 1) {
        await sleep(EMBEDDING_BACKOFF_MS[attempt]);
      }
    }
  }
  throw new EmbeddingError(
    `Embedding failed after ${EMBEDDING_MAX_RETRIES} attempts: ${lastErr instanceof Error ? lastErr.message : "unknown"}`,
  );
}

export const EMBEDDING_METHOD = "LocalHash-1024"; // logical name surfaced in metadata
