/**
 * RetrievalModule — Hybrid Search logic. STRICT MODULE BOUNDARY:
 *   - This module ONLY owns retrieval scoring. It never chunks, never embeds,
 *     never persists (the orchestrator does). Called by the orchestrator.
 *   (Mirrors services/retrieval.py from backend-directory-structure spec.)
 *
 * Pipeline (Backend §7.4):
 *   1. Embed query (caller-provided vector)
 *   2. Parent-level vector search (cosine) → top-K candidates
 *   3. Optional BM25 over chunk texts
 *   4. Fusion:
 *        • manual mode:  score = alpha * vScore + beta * bm25Score   (beta = 1 - alpha)
 *        • autoTune mode (construction note #2): sweep alpha ∈ {0.1..0.9},
 *          for each alpha compute fused scores, pick the alpha whose TOP-1
 *          result has the highest fused similarity. Return that alpha + results.
 *   5. Optional LLM reranker on top-N (z-ai-web-dev-sdk)
 *   6. Return scored results + full metadata
 */

import { db } from "@/lib/db";
import ZAI from "z-ai-web-dev-sdk";
import { ADAPTIVE_ALPHA_GRID, RERANKER_MODEL } from "./constants";
import { RerankError } from "./errors";
import {
  buildBM25Index,
  bm25SearchRanked,
} from "./bm25";
import {
  cosine,
  minMaxNormalize,
  weightedFuse,
} from "./vectors";
import { preview, timed, timedSync } from "./utils";
import type {
  SearchConfig,
  SearchMetadata,
  SearchResult,
  SearchResponse,
} from "./types";
import { logPipelineEvent } from "./errors";

interface RetrievalCandidate {
  chunkId: string;
  parentId: string;
  experimentId: string;
  chunkIndex: number;
  text: string;
  tokenCount: number;
  chunkMethod: string;
  embeddingMethod: string;
  parentSourceFile: string;
  parentText: string;
  section: string | null;
  chunkingTimeMs: number;
  embeddingTimeMs: number;
  vectorScore: number;
  bm25Score: number | null;
  fusedScore: number; // set during fusion
}

export interface HybridSearchInput {
  queryVector: number[];
  rawQuery: string;
  config: SearchConfig;
  experimentId?: string | null;
  searchId: string;
}

export interface HybridSearchOutput {
  results: SearchResult[];
  metadata: Omit<SearchMetadata, "searchId" | "experimentId" | "config">;
  bestAlpha: number | null;
}

/** Load candidates (chunk-level, includes parent text for context). */
async function loadCandidates(opts: {
  experimentId?: string | null;
  queryVector: number[];
  topK: number;
}): Promise<{ candidates: RetrievalCandidate[]; vectorSearchMs: number }> {
  const [raw, vectorSearchMs] = await timed(async () => {
    // Search across all chunks of the experiment (or all if no experimentId).
    const where = opts.experimentId ? { experimentId: opts.experimentId } : {};
    const chunks = await db.knowledgeChunk.findMany({
      where,
      include: { parent: true },
    });
    return chunks.map((c) => {
      const v = JSON.parse(c.vector) as number[];
      return {
        chunkId: c.id,
        parentId: c.parentId,
        experimentId: c.experimentId,
        chunkIndex: c.chunkIndex,
        text: c.text,
        tokenCount: c.tokenCount,
        chunkMethod: c.chunkMethod,
        embeddingMethod: c.embeddingMethod,
        parentSourceFile: c.parent.sourceFile,
        parentText: c.parent.text,
        section: c.section,
        chunkingTimeMs: c.chunkingTimeMs,
        embeddingTimeMs: c.embeddingTimeMs,
        vectorScore: cosine(opts.queryVector, v),
        bm25Score: null as number | null,
        fusedScore: 0,
      };
    });
  });
  // Sort by vector score, take topK (broader pool for fusion then rerank).
  const pool = Math.max(opts.topK * 3, 20);
  const candidates = raw.sort((a, b) => b.vectorScore - a.vectorScore).slice(0, pool);
  return { candidates, vectorSearchMs };
}

/** Add BM25 scores to candidates. */
async function scoreWithBM25(
  candidates: RetrievalCandidate[],
  rawQuery: string,
): Promise<{ candidates: RetrievalCandidate[]; bm25Ms: number }> {
  const [ranked, bm25Ms] = timedSync(() => {
    const index = buildBM25Index(
      candidates.map((c) => ({ id: c.chunkId, text: c.text })),
    );
    return bm25SearchRanked(index, rawQuery);
  });
  const scoreMap = new Map(ranked.map((r) => [r.id, r.score]));
  return {
    candidates: candidates.map((c) => ({
      ...c,
      bm25Score: scoreMap.get(c.chunkId) ?? 0,
    })),
    bm25Ms,
  };
}

/**
 * Fuse scores for a given alpha. Returns candidates sorted by fused score.
 * If BM25 is off, fusedScore = vectorScore (alpha=1 effectively).
 */
function fuseWithAlpha(candidates: RetrievalCandidate[], alpha: number, useBm25: boolean) {
  return candidates
    .map((c): RetrievalCandidate => ({
      ...c,
      fusedScore: useBm25 && c.bm25Score !== null
        ? weightedFuse(c.vectorScore, c.bm25Score, alpha)
        : c.vectorScore,
    }))
    .sort((a, b) => b.fusedScore - a.fusedScore);
}

/**
 * Adaptive alpha/beta sweep (construction note #2).
 * For each alpha in 0.1..0.9 (beta = 1 - alpha), compute fused scores and
 * record the top-1 fused similarity. Return the alpha with the highest top-1.
 */
function adaptiveSweep(candidates: RetrievalCandidate[]): { bestAlpha: number; topFused: number } {
  let bestAlpha = 0.5;
  let bestTop = -Infinity;
  for (const alpha of ADAPTIVE_ALPHA_GRID) {
    const fused = fuseWithAlpha(candidates, alpha, true);
    const top = fused[0]?.fusedScore ?? -Infinity;
    if (top > bestTop) {
      bestTop = top;
      bestAlpha = alpha;
    }
  }
  return { bestAlpha, topFused: bestTop };
}

/** LLM reranker (z-ai-web-dev-sdk). Scores relevance 0..1 via a structured prompt. */
async function rerankWithLLM(
  query: string,
  candidates: RetrievalCandidate[],
  topN: number,
): Promise<{ ranked: { candidate: RetrievalCandidate; rerankerScore: number }[]; rerankMs: number }> {
  const top = candidates.slice(0, Math.min(topN, candidates.length));
  if (top.length === 0) return { ranked: [], rerankMs: 0 };

  const [ranked, rerankMs] = await timed(async () => {
    try {
      const zai = await ZAI.create();
      // Build a structured prompt asking for per-candidate relevance scores 0..1.
      const docList = top
        .map((c, i) => `<<DOC_${i}>>\n${preview(c.text, 400)}`)
        .join("\n\n");
      const prompt = `You are a retrieval reranker. Score each document's relevance to the query on a scale of 0.0 to 1.0. Respond ONLY with a JSON array of numbers, one per document, in order. No explanation.

Query: ${query}

${docList}

Respond with JSON array of ${top.length} numbers in [0,1], e.g. [0.9, 0.3, ...]:`;

      const completion = await zai.chat.completions.create({
        messages: [
          { role: "system", content: "You are a precise retrieval reranker that outputs only JSON." },
          { role: "user", content: prompt },
        ],
        temperature: 0,
      });
      const content = completion?.choices?.[0]?.message?.content ?? "[]";
      // Extract JSON array from response (be lenient with surrounding text).
      const match = content.match(/\[[\s\S]*\]/);
      let scores: number[] = [];
      if (match) {
        try {
          scores = JSON.parse(match[0]) as number[];
        } catch {
          scores = [];
        }
      }
      // Fallback: if parsing failed or count mismatch, fall back to fused score.
      if (scores.length !== top.length) {
        logPipelineEvent({
          event: "reranker.fallback",
          reason: "score_count_mismatch",
          expected: top.length,
          got: scores.length,
        });
        scores = top.map((c) => c.fusedScore ?? c.vectorScore);
      }
      return top.map((c, i) => ({
        candidate: c,
        rerankerScore: Math.max(0, Math.min(1, Number(scores[i]) || 0)),
      }));
    } catch (err) {
      throw new RerankError(
        `LLM reranker failed: ${err instanceof Error ? err.message : "unknown"}`,
      );
    }
  });
  // Sort by reranker score desc.
  ranked.sort((a, b) => b.rerankerScore - a.rerankerScore);
  return { ranked, rerankMs };
}

/** Main hybrid search entry point. */
export async function hybridSearch(input: HybridSearchInput): Promise<HybridSearchOutput> {
  const t0 = performance.now();
  const { queryVector, rawQuery, config, experimentId, searchId } = input;

  // 1. Vector search (candidate pool)
  const { candidates, vectorSearchMs } = await loadCandidates({
    experimentId,
    queryVector,
    topK: config.topKVector,
  });

  if (candidates.length === 0) {
    return {
      results: [],
      metadata: {
        queryEmbeddingTimeMs: 0,
        vectorSearchTimeMs: vectorSearchMs,
        bm25SearchTimeMs: 0,
        rerankTimeMs: 0,
        totalSearchTimeMs: performance.now() - t0,
        bestAlpha: null,
        candidatesBeforeRerank: 0,
        resultsAfterRerank: 0,
      },
      bestAlpha: null,
    };
  }

  // 2. Optional BM25
  let bm25Ms = 0;
  let working = candidates;
  if (config.useBm25) {
    const r = await scoreWithBM25(candidates, rawQuery);
    working = r.candidates;
    bm25Ms = r.bm25Ms;
  }

  // 3. Fusion (manual or adaptive)
  let alphaUsed = config.hybridAlpha;
  let bestAlpha: number | null = null;
  if (config.autoTuneWeights && config.useBm25) {
    const sweep = adaptiveSweep(working);
    bestAlpha = sweep.bestAlpha;
    alphaUsed = sweep.bestAlpha;
    logPipelineEvent({
      event: "search.adaptive_sweep",
      searchId,
      bestAlpha,
      topFused: sweep.topFused,
    });
  }
  // Apply fusion with the chosen alpha.
  working = fuseWithAlpha(working, alphaUsed, config.useBm25);

  // 4. Optional reranker
  let rerankMs = 0;
  let finalRanked: { candidate: RetrievalCandidate; finalScore: number; rerankerScore: number | null }[] =
    working.map((c) => ({ candidate: c, finalScore: c.fusedScore, rerankerScore: null }));
  if (config.useReranker && config.topNRerank > 0) {
    const r = await rerankWithLLM(rawQuery, working, config.topNRerank);
    rerankMs = r.rerankMs;
    const rerankedIds = new Set(r.ranked.map((x) => x.candidate.chunkId));
    finalRanked = working.map((c) => {
      const rr = r.ranked.find((x) => x.candidate.chunkId === c.chunkId);
      return {
        candidate: c,
        finalScore: rr ? rr.rerankerScore : c.fusedScore * 0.5, // dampen non-reranked
        rerankerScore: rr ? rr.rerankerScore : null,
      };
    });
    // Sort: reranked first by reranker score, then the rest by fused score.
    finalRanked.sort((a, b) => {
      if (a.rerankerScore !== null && b.rerankerScore !== null) return b.rerankerScore - a.rerankerScore;
      if (a.rerankerScore !== null) return -1;
      if (b.rerankerScore !== null) return 1;
      return b.finalScore - a.finalScore;
    });
    // Keep only reranked + a few spares
    finalRanked = finalRanked.filter((x) => rerankedIds.has(x.candidate.chunkId)).concat(
      finalRanked.filter((x) => !rerankedIds.has(x.candidate.chunkId)).slice(0, 3),
    );
  } else {
    finalRanked.sort((a, b) => b.finalScore - a.finalScore);
  }

  // 5. Build SearchResult list with ranks
  const results: SearchResult[] = finalRanked.slice(0, Math.max(config.topKVector, config.topNRerank || 0)).map((x, i) => ({
    rank: i + 1,
    chunkId: x.candidate.chunkId,
    parentId: x.candidate.parentId,
    experimentId: x.candidate.experimentId,
    chunkIndex: x.candidate.chunkIndex,
    text: x.candidate.text,
    tokenCount: x.candidate.tokenCount,
    chunkMethod: x.candidate.chunkMethod,
    embeddingMethod: x.candidate.embeddingMethod,
    parentSourceFile: x.candidate.parentSourceFile,
    parentTextPreview: preview(x.candidate.parentText, 300),
    vectorScore: x.candidate.vectorScore,
    bm25Score: x.candidate.bm25Score,
    fusedScore: x.candidate.fusedScore,
    rerankerScore: x.rerankerScore,
    finalScore: x.finalScore,
    alphaUsed,
    betaUsed: 1 - alphaUsed,
    ...(x.candidate.section ? { section: x.candidate.section } : {}),
    chunkingTimeMs: x.candidate.chunkingTimeMs,
    embeddingTimeMs: x.candidate.embeddingTimeMs,
  }));

  return {
    results,
    metadata: {
      queryEmbeddingTimeMs: 0, // filled by orchestrator
      vectorSearchTimeMs: vectorSearchMs,
      bm25SearchTimeMs: bm25Ms,
      rerankTimeMs: rerankMs,
      totalSearchTimeMs: performance.now() - t0,
      bestAlpha,
      candidatesBeforeRerank: working.length,
      resultsAfterRerank: results.length,
    },
    bestAlpha,
  };
}

// Re-export for orchestrator
export { minMaxNormalize };
export const RERANKER_MODEL_NAME = RERANKER_MODEL;
