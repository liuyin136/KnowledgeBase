/**
 * Local-First RAG Experimentation Platform v1
 * Single source of truth for all shared types (mirrors API_Interface_Design_v1.1.md §2).
 * No runtime logic here — pure type + Zod contract definitions.
 */

import { z } from "zod";

// ─── Enums / constants (constants.ts content lives in ./constants) ─────────

export type ChunkMethod = "Recursive" | "Semantic" | "Structure-Aware";
export type EmbeddingApproach = "LongText" | "ChildChunk";
export type AdvOption = "None"; // v1 only
export type ExperimentStatus = "pending" | "running" | "completed" | "failed";
export type JobType = "ingest" | "search";
export type JobStatus = "queued" | "running" | "completed" | "failed";
export type ExperimentKind = "ingest" | "search";

// ─── Config contracts (API §2) ─────────────────────────────────────────────

export const IngestConfigSchema = z.object({
  embeddingApproach: z.enum(["LongText", "ChildChunk"]),
  chunkMethod: z.enum(["Recursive", "Semantic", "Structure-Aware"]),
  advOption: z.literal("None").default("None"),
});
export type IngestConfig = z.infer<typeof IngestConfigSchema>;

export const SearchConfigSchema = z.object({
  hybridAlpha: z.number().min(0).max(1).default(0.7),
  useBm25: z.boolean().default(true),
  topKVector: z.number().int().min(1).max(100).default(10),
  topNRerank: z.number().int().min(0).max(50).default(5),
  useReranker: z.boolean().default(false),
  parentContextLevels: z.number().int().min(0).max(5).default(1),
  // Construction note #2: adaptive alpha/beta sweep 0.1–0.9.
  autoTuneWeights: z.boolean().default(false),
});
export type SearchConfig = z.infer<typeof SearchConfigSchema>;

// ─── Metadata contracts (Backend §6) ───────────────────────────────────────

export interface ChunkMetadata {
  chunkId: string;
  parentDocId: string;
  chunkIndex: number;
  chunkMethod: string;
  embeddingMethod: string;
  tokenCount: number;
  chunkingTimeMs: number;
  embeddingTimeMs: number;
  charStart?: number;
  charEnd?: number;
  section?: string;
  textPreview: string;
  // Added for full document visibility on Experiments page
  text?: string;
  nodeType?: string; // 'knowledge' | 'knowledge_chunk'
  parentSourceFile?: string;
}

export interface ExperimentRun {
  experimentId: string;
  description: string;
  embeddingApproach: string;
  chunkMethod: string;
  totalChunks: number;
  avgTokensPerChunk: number;
  totalTimeMs: number;
  sourceFile: string;
  status: ExperimentStatus;
}

// ─── Search result contract (API §2) ───────────────────────────────────────

export interface SearchResult {
  rank: number;
  chunkId: string;
  parentId: string;
  experimentId: string;
  chunkIndex: number;
  text: string;
  tokenCount: number;
  chunkMethod: string;
  embeddingMethod: string;
  parentSourceFile: string;
  parentTextPreview: string;
  // Scores
  vectorScore: number;
  bm25Score: number | null;
  fusedScore: number;
  rerankerScore: number | null;
  finalScore: number;
  // Config snapshot used (for observability)
  alphaUsed: number;
  betaUsed: number;
  // Context
  section?: string;
  chunkingTimeMs: number;
  embeddingTimeMs: number;
}

export interface SearchMetadata {
  searchId: string;
  experimentId: string | null;
  queryEmbeddingTimeMs: number;
  vectorSearchTimeMs: number;
  bm25SearchTimeMs: number;
  rerankTimeMs: number;
  totalSearchTimeMs: number;
  config: SearchConfig;
  bestAlpha: number | null; // when autoTuneWeights
  candidatesBeforeRerank: number;
  resultsAfterRerank: number;
}

export interface SearchResponse {
  searchId: string;
  results: SearchResult[];
  metadata: SearchMetadata;
}

// ─── Memory contracts (API §2) ─────────────────────────────────────────────

export interface Memory {
  id: string;
  userQueryId: string;
  experimentId: string | null;
  chunkId: string | null;
  queryText: string;
  chunkText: string | null;
  score: number | null;
  vectorScore: number | null;
  bm25Score: number | null;
  fusedScore: number | null;
  rerankerScore: number | null;
  notes: string | null;
  successScore: number | null;
  createdAt: string;
  selected: boolean; // whether currently in a cart (denormalized for UI)
}

export interface MemoryCart {
  id: string;
  name: string;
  description: string | null;
  memoryCount: number;
  createdAt: string;
  updatedAt: string;
}

// ─── Job / progress contracts (API §5) ─────────────────────────────────────

export interface IngestProgressEvent {
  index: number;
  total: number;
  progress: number; // 0-100
  chunk: ChunkMetadata | null; // null for non-chunk events (start/done)
  stage: "chunking" | "embedding" | "persisting" | "done" | "error";
  message?: string;
}

export interface JobStatusResponse {
  jobId: string;
  type: JobType;
  experimentId: string | null;
  status: JobStatus;
  progress: number;
  current: number;
  total: number;
  events: IngestProgressEvent[];
  errorCode: string | null;
  errorMessage: string | null;
  result: SearchResponse | null; // for search jobs
}

// ─── Error contract (API §4, error-handling spec §1) ───────────────────────

export interface ErrorBody {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

// ─── Pagination (API §3) ───────────────────────────────────────────────────

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
  hasMore: boolean;
}

// ─── Document text (for :Knowledge raw visibility in Experiments) ──────────
export interface DocumentTextResponse {
  sourceFile: string;
  text: string | null;
  kind?: string; // 'upload' | 'knowledge' | 'fallback'
  embeddingMethod?: string;
  experimentId?: string | null;
  id?: string;
  createdAt?: string;
}
