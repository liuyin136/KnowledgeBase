"""
core/constants.py — Enums + immutable constants for the RAG platform v1.2.

Mirrors `src/lib/rag/constants.ts` (the JS-side single source of truth) so the
FastAPI backend emits identical contract values.

Includes:
  • ChunkMethod, EmbeddingApproach, AdvOption, ExperimentStatus, JobType, JobStatus enums
  • EMBEDDING_DIM (1024 — BGE-M3, per neo4j-schema-v1.1.md §3)
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


# ─── Embedding / models ───────────────────────────────────────────────────────

EMBEDDING_MODEL = "BAAI/bge-m3"  # logical model name for observability
EMBEDDING_DIM = 1024  # BGE-M3 output dim (matches neo4j-schema-v1.1.md §3)
RERANKER_MODEL = "BAAI/bge-reranker-base"

# ─── Chunking targets (mirror src/lib/rag/constants.ts) ───────────────────────

CHUNK_TARGET_TOKENS = {
    ChunkMethod.RECURSIVE.value: 512,
    ChunkMethod.SEMANTIC.value: 400,
    ChunkMethod.STRUCTURE_AWARE.value: 600,
}
CHUNK_OVERLAP_TOKENS = 64
LONGTEXT_WINDOW_TOKENS = 8000
LONGTEXT_OVERLAP_TOKENS = 800

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
LABEL_EXPERIMENT = "Experiment"

# Relationship types
REL_HAS_CHUNK = "HAS_CHUNK"
REL_TRIGGERED = "TRIGGERED"
REL_RETRIEVED = "RETRIEVED"
REL_CONTAINS = "CONTAINS"

# ─── Embedding method tags (stored on node properties) ───────────────────────

EMBEDDING_METHOD_LONGTEXT = "LongText"
EMBEDDING_METHOD_CHILDCHUNK = "ChildChunk"
