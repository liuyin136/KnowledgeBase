"""
core/constants.py — Enums + immutable constants for the RAG platform v1.3.

Mirrors `src/lib/rag/constants.ts` (the JS-side single source of truth) so the
FastAPI backend emits identical contract values.

Includes:
  • ChunkMethod, EmbeddingApproach, AdvOption, ExperimentStatus, JobType, JobStatus enums
  • EMBEDDING_MODEL / RERANKER_MODEL (v1.3 — Jina v5 small + Jina Reranker v3 default)
  • EMBEDDING_DIM (1024 — kept STABLE for both Jina + BGE-M3; Jina uses Matryoshka truncation)
  • Jina task-conditioning constants (retrieval.query / retrieval.passages)
  • ADAPTIVE_ALPHA_GRID (construction note #2: 0.1..0.9)
  • Error codes (mirror ERROR_CODES in constants.ts)
  • Retry config (embedding max 3 attempts, exp backoff 1s/2s/4s)
  • Pagination defaults
  • Chunking target/overlap token counts
"""

from __future__ import annotations

from enum import Enum

# ─── Enums ────────────────────────────────────────────────────────────────────


class ChunkMethod(str, Enum):
    """v1 standard chunking methods (NO Late/Agentic — guardrail)."""

    RECURSIVE = "Recursive"
    SEMANTIC = "Semantic"
    STRUCTURE_AWARE = "Structure-Aware"


class LongTextMethod(str, Enum):
    """Internal: LongText sliding-window chunking (used by the LongText path)."""

    LONGTEXT = "LongText"


class EmbeddingApproach(str, Enum):
    """v1 embedding approaches."""

    LONGTEXT = "LongText"
    CHILDCHUNK = "ChildChunk"


class AdvOption(str, Enum):
    """v1 advanced option (always None)."""

    NONE = "None"


class ExperimentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ExperimentKind(str, Enum):
    INGEST = "ingest"
    SEARCH = "search"


class JobType(str, Enum):
    INGEST = "ingest"
    SEARCH = "search"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class IngestStage(str, Enum):
    """Stages emitted in IngestProgressEvent (mirror TS IngestProgressEvent.stage)."""

    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    PERSISTING = "persisting"
    DONE = "done"
    ERROR = "error"


# ─── Embedding / models (v1.3 — Jina default + BGE-M3 toggle) ─────────────────
# v1.3 migration: default is Jina v5 (small) + Jina Reranker v3. BGE-M3 and
# BGE-reranker-base remain available as toggleable alternatives via
# EMBEDDING_MODEL / RERANKER_MODEL env vars (see core/config.py).
#
# The Neo4j vector indexes stay 1024-dim for BOTH models — Jina v5 small natively
# outputs 1536 dims but is invoked with Matryoshka truncation (`dimensions=1024`).
# BGE-M3 is natively 1024-dim. The two model families therefore write into the
# SAME vector indexes without re-creation (caveat: vectors are still
# model-specific, so switching models requires re-ingesting documents).
EMBEDDING_MODEL = "jinaai/jina-embeddings-v5-text-small"  # active repo id (v1.3 default)
EMBEDDING_MODEL_LOGICAL = "jina-v5-small"  # logical id used in EMBEDDING_MODEL env var
EMBEDDING_DIM = 1024  # Neo4j vector index dim — Jina v5 small (Matryoshka truncated to 1024)
RERANKER_MODEL = "jinaai/jina-reranker-v3"  # active repo id (v1.3 default)
RERANKER_MODEL_LOGICAL = "jina-v3"  # logical id used in RERANKER_MODEL env var

# Alternative (BGE-M3) constants — kept for reference + downstream tooling.
BGE_M3_REPO = "BAAI/bge-m3"
BGE_RERANKER_REPO = "BAAI/bge-reranker-base"

# Jina Embeddings v5 is task-conditioned. The orchestrator passes `is_query=True`
# for queries and `is_query=False` (default) for passages/documents; the embedder
# maps that to the corresponding Jina task string. BGE-M3 ignores the task param.
JINA_TASK_QUERY = "retrieval"
JINA_TASK_PASSAGE = "retrieval"  # encode uses task="retrieval" (prompt_name not supported in this ST integration)

# Native output dims (per model). Used only for observability — the ACTUAL dim
# written to Neo4j is EMBEDDING_DIM (1024) via Matryoshka truncation for Jina v5.
JINA_V5_SMALL_NATIVE_DIM = 1536
BGE_M3_NATIVE_DIM = 1024

# ─── Chunking targets (mirror src/lib/rag/constants.ts) ───────────────────────

CHUNK_TARGET_TOKENS = {
    ChunkMethod.RECURSIVE.value: 512,
    ChunkMethod.SEMANTIC.value: 400,
    ChunkMethod.STRUCTURE_AWARE.value: 600,
}
CHUNK_OVERLAP_TOKENS = 64
LONGTEXT_WINDOW_TOKENS = 30000
LONGTEXT_OVERLAP_TOKENS = 3000

# ─── Retry policy (per error-handling-retry-strategy_v1.1.md §3) ──────────────

EMBEDDING_MAX_RETRIES = 3
EMBEDDING_BACKOFF_MS = [1000, 2000, 4000]  # exp backoff: 1s → 2s → 4s
NEO4J_MAX_RETRIES = 2  # transient DB errors

# ─── Adaptive α/β sweep grid (construction note #2) ───────────────────────────
# alpha = vector weight, beta = 1 - alpha = BM25 weight.
# Sweep alpha ∈ {0.1, ..., 0.9}; pick the alpha whose TOP-1 fused score is highest.
ADAPTIVE_ALPHA_GRID = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
DEFAULT_HYBRID_ALPHA = 0.7

# ─── Error codes (mirror src/lib/rag/constants.ts ERROR_CODES) ────────────────

ERROR_CODES = {
    "VALIDATION_ERROR": "VALIDATION_ERROR",
    "NOT_FOUND": "NOT_FOUND",
    "INGEST_FAILED": "INGEST_FAILED",
    "EMBEDDING_FAILED": "EMBEDDING_FAILED",
    "NEO4J_ERROR": "NEO4J_ERROR",
    "SEARCH_FAILED": "SEARCH_FAILED",
    "RERANK_FAILED": "RERANK_FAILED",
    "JOB_NOT_FOUND": "JOB_NOT_FOUND",
    "INTERNAL_ERROR": "INTERNAL_ERROR",
}

# ─── Pagination ───────────────────────────────────────────────────────────────

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# ─── Node labels (Neo4j) ─────────────────────────────────────────────────────

LABEL_KNOWLEDGE = "Knowledge"
LABEL_KNOWLEDGE_CHUNK = "KnowledgeChunk"
LABEL_USER_QUERY = "UserQuery"
LABEL_USER_QUERY_CHUNK = "UserQueryChunk"
LABEL_MEMORY = "Memory"
LABEL_MEMORY_CART = "MemoryCart"

# Relationship types
REL_HAS_CHUNK = "HAS_CHUNK"
REL_TRIGGERED = "TRIGGERED"
REL_RETRIEVED = "RETRIEVED"
REL_CONTAINS = "CONTAINS"

# ─── Embedding method tags (stored on node properties) ───────────────────────

EMBEDDING_METHOD_LONGTEXT = "LongText"
EMBEDDING_METHOD_CHILDCHUNK = "ChildChunk"
