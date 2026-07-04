/**
 * Constants & enums for RAG platform v1.
 * Mirrors core/constants.py from backend-directory-structure spec.
 */

export const EMBEDDING_MODEL = "z-ai-embedding-v1"; // logical model name for observability
export const EMBEDDING_DIM = 1024; // matches BGE-M3 spec in neo4j-schema-v1.1
export const RERANKER_MODEL = "z-ai-llm-reranker";

export const CHUNK_TARGET_TOKENS: Record<string, number> = {
  Recursive: 512,
  Semantic: 400,
  "Structure-Aware": 600,
};

export const CHUNK_OVERLAP_TOKENS = 64;
export const LONGTEXT_WINDOW_TOKENS = 8000; // sliding window for LongText path
export const LONGTEXT_OVERLAP_TOKENS = 800; // 10%

export const EMBEDDING_MAX_RETRIES = 3;
export const EMBEDDING_BACKOFF_MS = [1000, 2000, 4000]; // exp backoff per error-handling spec §3
export const NEO4J_MAX_RETRIES = 2; // (DB writes) — adapted to Prisma

export const ERROR_CODES = {
  VALIDATION_ERROR: "VALIDATION_ERROR",
  NOT_FOUND: "NOT_FOUND",
  INGEST_FAILED: "INGEST_FAILED",
  EMBEDDING_FAILED: "EMBEDDING_FAILED",
  NEO4J_ERROR: "NEO4J_ERROR", // kept for contract fidelity (maps to DB_ERROR in this stack)
  DB_ERROR: "DB_ERROR",
  SEARCH_FAILED: "SEARCH_FAILED",
  RERANK_FAILED: "RERANK_FAILED",
  JOB_NOT_FOUND: "JOB_NOT_FOUND",
  INTERNAL_ERROR: "INTERNAL_ERROR",
} as const;

export type ErrorCode = (typeof ERROR_CODES)[keyof typeof ERROR_CODES];

// Adaptive weight sweep grid (construction note #2): alpha 0.1..0.9, beta = 1 - alpha
export const ADAPTIVE_ALPHA_GRID = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9];

// Default pagination
export const DEFAULT_PAGE_SIZE = 20;
export const MAX_PAGE_SIZE = 100;
