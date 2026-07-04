/**
 * MetadataService — pure factory functions for standardized metadata.
 * STRICT MODULE BOUNDARY: produces metadata dicts only; never persists.
 *   (Mirrors services/metadata.py from backend-directory-structure spec.)
 *
 * Per Backend §6, every run produces:
 *   • ChunkMetadata (chunk_id, parent_doc_id, chunk_method, embedding_method,
 *     token_count, timings, experiment_id, char range, section, text preview)
 *   • ExperimentRun (experiment_id, description, embedding_approach,
 *     chunk_method, total_chunks, avg_tokens, total_time_ms, source_file, status)
 */

import type { ChunkMetadata, ExperimentRun } from "./types";
import { preview } from "./utils";

export interface CreateChunkMetadataInput {
  chunkId: string;
  parentDocId: string;
  experimentId: string;
  chunkIndex: number;
  chunkMethod: string;
  embeddingMethod: string;
  tokenCount: number;
  chunkingTimeMs: number;
  embeddingTimeMs: number;
  charStart?: number;
  charEnd?: number;
  section?: string;
  text: string;
}

export function createChunkMetadata(input: CreateChunkMetadataInput): ChunkMetadata {
  return {
    chunkId: input.chunkId,
    parentDocId: input.parentDocId,
    experimentId: input.experimentId,
    chunkIndex: input.chunkIndex,
    chunkMethod: input.chunkMethod,
    embeddingMethod: input.embeddingMethod,
    tokenCount: input.tokenCount,
    chunkingTimeMs: Math.round(input.chunkingTimeMs * 1000) / 1000,
    embeddingTimeMs: Math.round(input.embeddingTimeMs * 1000) / 1000,
    ...(input.charStart !== undefined ? { charStart: input.charStart } : {}),
    ...(input.charEnd !== undefined ? { charEnd: input.charEnd } : {}),
    ...(input.section ? { section: input.section } : {}),
    textPreview: preview(input.text, 220),
  };
}

export interface CreateExperimentRunInput {
  experimentId: string;
  description: string;
  embeddingApproach: string;
  chunkMethod: string;
  totalChunks: number;
  avgTokensPerChunk: number;
  totalTimeMs: number;
  sourceFile: string;
  status: ExperimentRun["status"];
}

export function createExperimentRun(input: CreateExperimentRunInput): ExperimentRun {
  return {
    experimentId: input.experimentId,
    description: input.description,
    embeddingApproach: input.embeddingApproach,
    chunkMethod: input.chunkMethod,
    totalChunks: input.totalChunks,
    avgTokensPerChunk: Math.round(input.avgTokensPerChunk * 100) / 100,
    totalTimeMs: Math.round(input.totalTimeMs * 1000) / 1000,
    sourceFile: input.sourceFile,
    status: input.status,
  };
}

/** Compute aggregate stats from a list of chunk metadatas. */
export function aggregateChunkStats(
  chunks: { tokenCount: number; chunkingTimeMs: number; embeddingTimeMs: number }[],
): { totalChunks: number; avgTokens: number; totalChunkingMs: number; totalEmbeddingMs: number } {
  const totalChunks = chunks.length;
  if (totalChunks === 0) {
    return { totalChunks: 0, avgTokens: 0, totalChunkingMs: 0, totalEmbeddingMs: 0 };
  }
  const totalTokens = chunks.reduce((s, c) => s + c.tokenCount, 0);
  const totalChunkingMs = chunks.reduce((s, c) => s + c.chunkingTimeMs, 0);
  const totalEmbeddingMs = chunks.reduce((s, c) => s + c.embeddingTimeMs, 0);
  return {
    totalChunks,
    avgTokens: totalTokens / totalChunks,
    totalChunkingMs,
    totalEmbeddingMs,
  };
}
