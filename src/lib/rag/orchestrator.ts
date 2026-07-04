/**
 * PipelineOrchestrator — thin coordination layer. STRICT MODULE BOUNDARY:
 *   - Owns coordination, timing, metadata emission, transactions, experiment lifecycle.
 *   - Calls ChunkingModule (boundaries), EmbeddingModule (vectors), RetrievalModule
 *     (scoring), MetadataService (metadata), Store (persistence).
 *   - NEVER finds boundaries itself, NEVER produces vectors itself, NEVER scores itself.
 *   (Mirrors services/orchestrator.py from backend-directory-structure spec.)
 *
 * Two flows:
 *   • ingestLongText(document, config, experimentId) — Slice 1
 *   • ingestChildChunk(document, config, experimentId) — Slice 2
 *   • runSearch(rawQuery, config, experimentId)       — Slice 4+5
 */

import { db } from "@/lib/db";
import {
  determineBoundaries,
  chunkLongText,
  type ChunkBoundary,
} from "./chunking";
import { embedWithRetry, embedText, EMBEDDING_METHOD } from "./embedding";
import { createChunkMetadata, createExperimentRun, aggregateChunkStats } from "./metadata";
import { hybridSearch } from "./retrieval";
import * as store from "./store";
import {
  appendEvent,
  createJob,
  markCompleted,
  markFailed,
  markRunning,
} from "./jobs";
import { logPipelineEvent, logPipelineError, IngestError } from "./errors";
import { approxTokenCount, preview, timed } from "./utils";
import type {
  ChunkMetadata,
  IngestConfig,
  IngestProgressEvent,
  SearchConfig,
  SearchResponse,
} from "./types";

// ─── Ingest: LongText (Slice 1) ─────────────────────────────────────────────

export async function ingestLongText(opts: {
  jobId: string;
  experimentId: string;
  documentId: string;
  filename: string;
  text: string;
  config: IngestConfig;
}): Promise<void> {
  const { jobId, experimentId, documentId, filename, text, config } = opts;
  await markRunning(jobId, 3);
  await store.updateExperimentStatus(experimentId, "running");
  logPipelineEvent({ event: "ingest.start", experimentId, jobId, approach: "LongText", filename });

  try {
    // 1. Chunk (LongText sliding window)
    const [boundaries, chunkingMs] = await timed(() => Promise.resolve(chunkLongText(text)));
    const total = Math.max(boundaries.length, 1);
    await appendEvent(jobId, {
      index: 0, total, progress: 5, chunk: null, stage: "chunking",
      message: `LongText windowing produced ${boundaries.length} segment(s) in ${chunkingMs.toFixed(1)}ms`,
    });

    // 2. Embed + persist each window as a Knowledge node (+ single KnowledgeChunk mirroring it)
    const chunksMeta: ChunkMetadata[] = [];
    const embeddingMethod = "LongText";
    let knowledgeId: string | null = null;

    for (let i = 0; i < boundaries.length; i++) {
      const b = boundaries[i];
      const { vector, timeMs: embMs, retries } = await embedWithRetry(b.text, { experimentId, stage: "embedding" });
      // First window → create the parent Knowledge node with its own long-text vector.
      if (i === 0) {
        const parentVec = await embedWithRetry(text, { experimentId, stage: "embedding" });
        knowledgeId = await store.createKnowledge({
          experimentId,
          sourceFile: filename,
          text,
          totalTokens: approxTokenCount(text),
          vector: parentVec.vector,
          embeddingTimeMs: parentVec.timeMs,
        });
      }
      // Each window is also stored as a KnowledgeChunk (so retrieval has a uniform target).
      const chunkId = await store.createChunk({
        experimentId,
        parentId: knowledgeId!,
        chunkIndex: b.index,
        text: b.text,
        tokenCount: b.tokenCount,
        chunkMethod: "LongText",
        chunkingTimeMs: chunkingMs / Math.max(boundaries.length, 1),
        embeddingMethod,
        embeddingTimeMs: embMs,
        vector,
        charStart: b.charStart,
        charEnd: b.charEnd,
      });
      const meta = createChunkMetadata({
        chunkId, parentDocId: knowledgeId!, experimentId,
        chunkIndex: b.index, chunkMethod: "LongText", embeddingMethod,
        tokenCount: b.tokenCount, chunkingTimeMs: chunkingMs / Math.max(boundaries.length, 1),
        embeddingTimeMs: embMs, charStart: b.charStart, charEnd: b.charEnd, text: b.text,
      });
      chunksMeta.push(meta);
      const progress = 10 + Math.floor(((i + 1) / total) * 80);
      const ev: IngestProgressEvent = {
        index: i + 1, total, progress, chunk: meta, stage: "embedding",
        message: `Embedded window ${i + 1}/${total} (${b.tokenCount} tok, ${embMs.toFixed(1)}ms${retries ? `, ${retries} retries` : ""})`,
      };
      await appendEvent(jobId, ev);
      await store.updateExperimentStatus(experimentId, "running");
    }

    // 3. Finalize experiment metadata
    const stats = aggregateChunkStats(chunksMeta);
    const totalTimeMs = chunkingMs + chunksMeta.reduce((s, c) => s + c.embeddingTimeMs, 0);
    const run = createExperimentRun({
      experimentId, description: `LongText ingest of ${filename}`,
      embeddingApproach: "LongText", chunkMethod: "LongText",
      totalChunks: stats.totalChunks, avgTokensPerChunk: stats.avgTokens,
      totalTimeMs, sourceFile: filename, status: "completed",
    });
    await store.updateExperimentStatus(experimentId, "completed", {
      totalChunks: run.totalChunks,
      avgTokensPerChunk: run.avgTokensPerChunk,
      totalTimeMs: run.totalTimeMs,
    });
    await appendEvent(jobId, {
      index: total, total, progress: 100, chunk: null, stage: "done",
      message: `Ingest complete: ${run.totalChunks} chunk(s), avg ${run.avgTokensPerChunk.toFixed(0)} tok, ${run.totalTimeMs.toFixed(0)}ms total`,
    });
    await markCompleted(jobId);
    logPipelineEvent({ event: "ingest.completed", experimentId, jobId, run });
  } catch (err) {
    const code = err instanceof Error ? "INGEST_FAILED" : "INTERNAL_ERROR";
    const message = err instanceof Error ? err.message : "unknown";
    logPipelineError({ experimentId, stage: "orchestrator", err });
    await store.updateExperimentStatus(experimentId, "failed", { errorCode: code, errorMessage: message });
    await appendEvent(jobId, { index: 0, total: 0, progress: 0, chunk: null, stage: "error", message });
    await markFailed(jobId, code, message);
    throw new IngestError(message);
  }
}

// ─── Ingest: ChildChunk (Slice 2) ───────────────────────────────────────────

export async function ingestChildChunk(opts: {
  jobId: string;
  experimentId: string;
  documentId: string;
  filename: string;
  text: string;
  config: IngestConfig;
}): Promise<void> {
  const { jobId, experimentId, filename, text, config } = opts;
  await markRunning(jobId, 4);
  await store.updateExperimentStatus(experimentId, "running");
  logPipelineEvent({ event: "ingest.start", experimentId, jobId, approach: "ChildChunk", method: config.chunkMethod, filename });

  try {
    // 1. Chunk (Recursive / Semantic / Structure-Aware)
    const [boundaries, chunkingMs] = await timed(() =>
      Promise.resolve(determineBoundaries(text, config.chunkMethod)),
    );
    const total = boundaries.length;
    if (total === 0) throw new IngestError("Chunking produced 0 boundaries");
    await appendEvent(jobId, {
      index: 0, total, progress: 5, chunk: null, stage: "chunking",
      message: `${config.chunkMethod} produced ${total} chunk(s) in ${chunkingMs.toFixed(1)}ms`,
    });

    // 2. Create parent Knowledge node (long-text vector for parent context + BM25)
    const parentVec = await embedWithRetry(text, { experimentId, stage: "embedding" });
    const knowledgeId = await store.createKnowledge({
      experimentId, sourceFile: filename, text,
      totalTokens: approxTokenCount(text),
      vector: parentVec.vector, embeddingTimeMs: parentVec.timeMs,
    });

    // 3. Embed + persist each child chunk
    const chunksMeta: ChunkMetadata[] = [];
    for (let i = 0; i < boundaries.length; i++) {
      const b = boundaries[i];
      const { vector, timeMs: embMs, retries } = await embedWithRetry(b.text, { experimentId, stage: "embedding" });
      const chunkId = await store.createChunk({
        experimentId, parentId: knowledgeId, chunkIndex: b.index,
        text: b.text, tokenCount: b.tokenCount,
        chunkMethod: config.chunkMethod,
        chunkingTimeMs: chunkingMs / total,
        embeddingMethod: "ChildChunk", embeddingTimeMs: embMs,
        vector, charStart: b.charStart, charEnd: b.charEnd,
        ...(b.section ? { section: b.section } : {}),
      });
      const meta = createChunkMetadata({
        chunkId, parentDocId: knowledgeId, experimentId,
        chunkIndex: b.index, chunkMethod: config.chunkMethod, embeddingMethod: "ChildChunk",
        tokenCount: b.tokenCount, chunkingTimeMs: chunkingMs / total, embeddingTimeMs: embMs,
        charStart: b.charStart, charEnd: b.charEnd, ...(b.section ? { section: b.section } : {}),
        text: b.text,
      });
      chunksMeta.push(meta);
      const progress = 10 + Math.floor(((i + 1) / total) * 80);
      await appendEvent(jobId, {
        index: i + 1, total, progress, chunk: meta, stage: "embedding",
        message: `Embedded chunk ${i + 1}/${total} (${b.tokenCount} tok, ${embMs.toFixed(1)}ms${retries ? `, ${retries} retries` : ""})`,
      });
    }

    // 4. Finalize
    const stats = aggregateChunkStats(chunksMeta);
    const totalTimeMs = chunkingMs + chunksMeta.reduce((s, c) => s + c.embeddingTimeMs, 0);
    await store.updateExperimentStatus(experimentId, "completed", {
      totalChunks: stats.totalChunks,
      avgTokensPerChunk: stats.avgTokens,
      totalTimeMs,
    });
    await appendEvent(jobId, {
      index: total, total, progress: 100, chunk: null, stage: "done",
      message: `Ingest complete: ${stats.totalChunks} chunk(s), avg ${stats.avgTokens.toFixed(0)} tok, ${totalTimeMs.toFixed(0)}ms total`,
    });
    await markCompleted(jobId);
    logPipelineEvent({ event: "ingest.completed", experimentId, jobId, totalChunks: stats.totalChunks });
  } catch (err) {
    const message = err instanceof Error ? err.message : "unknown";
    logPipelineError({ experimentId, stage: "orchestrator", err });
    await store.updateExperimentStatus(experimentId, "failed", { errorCode: "INGEST_FAILED", errorMessage: message });
    await appendEvent(jobId, { index: 0, total: 0, progress: 0, chunk: null, stage: "error", message });
    await markFailed(jobId, "INGEST_FAILED", message);
    throw new IngestError(message);
  }
}

// ─── Search (Slice 4+5) ─────────────────────────────────────────────────────

export async function runSearch(opts: {
  jobId: string;
  searchId: string;
  rawQuery: string;
  config: SearchConfig;
  experimentId?: string | null;
}): Promise<SearchResponse> {
  const { jobId, searchId, rawQuery, config, experimentId } = opts;
  await markRunning(jobId, 3);
  logPipelineEvent({ event: "search.start", jobId, searchId, experimentId });

  try {
    // 1. Embed query
    const [queryVec, queryEmbMs] = await timed(() =>
      embedWithRetry(rawQuery, { experimentId, stage: "embedding" }),
    );

    // 2. Hybrid search
    const out = await hybridSearch({
      queryVector: queryVec.vector,
      rawQuery,
      config,
      experimentId,
      searchId,
    });

    // 3. Persist UserQuery node + Memory nodes (one per result, for cart curation)
    const userQueryId = await store.createUserQuery({
      experimentId: experimentId ?? null,
      text: rawQuery,
      totalTokens: approxTokenCount(rawQuery),
      vector: queryVec.vector,
      embeddingTimeMs: queryEmbMs,
    });
    for (const r of out.results) {
      await store.createMemory({
        userQueryId,
        experimentId: r.experimentId,
        chunkId: r.chunkId,
        queryText: rawQuery,
        chunkText: r.text,
        vectorScore: r.vectorScore,
        bm25Score: r.bm25Score,
        fusedScore: r.fusedScore,
        rerankerScore: r.rerankerScore,
        score: r.finalScore,
      });
    }

    // 4. Persist SearchRun (history)
    await store.createSearchRun({
      experimentId: experimentId ?? null,
      rawQuery,
      config: {
        hybridAlpha: config.hybridAlpha,
        useBm25: config.useBm25,
        useReranker: config.useReranker,
        topKVector: config.topKVector,
        topNRerank: config.topNRerank,
        parentContextLevels: config.parentContextLevels,
        autoTuneWeights: config.autoTuneWeights,
      },
      bestAlpha: out.bestAlpha,
      resultCount: out.results.length,
      topScore: out.results[0]?.finalScore ?? null,
      searchTimeMs: out.metadata.totalSearchTimeMs,
    });

    const response: SearchResponse = {
      searchId,
      results: out.results,
      metadata: {
        searchId,
        experimentId: experimentId ?? null,
        queryEmbeddingTimeMs: queryEmbMs,
        vectorSearchTimeMs: out.metadata.vectorSearchTimeMs,
        bm25SearchTimeMs: out.metadata.bm25SearchTimeMs,
        rerankTimeMs: out.metadata.rerankTimeMs,
        totalSearchTimeMs: out.metadata.totalSearchTimeMs,
        config,
        bestAlpha: out.bestAlpha,
        candidatesBeforeRerank: out.metadata.candidatesBeforeRerank,
        resultsAfterRerank: out.metadata.resultsAfterRerank,
      },
    };
    await markCompleted(jobId, response);
    logPipelineEvent({
      event: "search.completed", jobId, searchId,
      resultCount: out.results.length, bestAlpha: out.bestAlpha,
    });
    return response;
  } catch (err) {
    const message = err instanceof Error ? err.message : "unknown";
    logPipelineError({ experimentId, stage: "retrieval", err });
    await markFailed(jobId, "SEARCH_FAILED", message);
    throw err;
  }
}

// Re-export for API layer convenience
export { embedText, EMBEDDING_METHOD, preview };
