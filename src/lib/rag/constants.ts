/**
 * Constants & enums for RAG platform v1.
 * Mirrors core/constants.py from backend-directory-structure spec.
 *
 * v1.3 model migration: default embedding is now Jina Embeddings v5 (small);
 * BGE-M3 remains available as a toggleable alternative. The Neo4j vector
 * indexes stay 1024-dim for BOTH models — Jina v5 small natively outputs 1536
 * dims but is invoked with Matryoshka truncation (`dimensions=1024`). BGE-M3
 * is natively 1024-dim. Both model families write into the SAME indexes.
 */

// Active embedding model — FORCED to Jina Embeddings v5 Text Small only (ingestion).
export const EMBEDDING_MODEL = "jinaai/jina-embeddings-v5-text-small";
export const EMBEDDING_MODEL_LOGICAL = "jina-v5-small";
export const EMBEDDING_DIM = 1024;
// Native output dim (for observability) — Jina v5 small = 1536.
export const JINA_V5_SMALL_NATIVE_DIM = 1536;

// Reranker — repo id (v1.3 default = Jina Reranker v3).
export const RERANKER_MODEL = "jinaai/jina-reranker-v3";
export const RERANKER_MODEL_LOGICAL = "jina-v3"; // logical id used in RERANKER_MODEL env var

// Reranker kept for reference (embedding is Jina v5 only).
export const BGE_RERANKER_REPO = "BAAI/bge-reranker-base";

// Jina Embeddings v5 (forced): backend uses task="retrieval" + prompt_name="document"|"query"
// for encode() during ingestion. These are legacy display constants.
export const JINA_TASK_QUERY = "retrieval";
export const JINA_TASK_PASSAGE = "retrieval";

export const CHUNK_TARGET_TOKENS: Record<string, number> = {
  Recursive: 512,
  Semantic: 400,
  "Structure-Aware": 600,
};

export const CHUNK_OVERLAP_TOKENS = 64;
export const LONGTEXT_WINDOW_TOKENS = 30000; // sliding window for LongText path
export const LONGTEXT_OVERLAP_TOKENS = 3000; // 10%

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
