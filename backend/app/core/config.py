"""
core/config.py — Pydantic Settings for the Local-First RAG Experimentation Platform v1.3.

All environment-driven configuration lives here. Single source of truth for:
  • Neo4j connection (URI/user/password)
  • Redis URL (job queue + progress tracking)
  • Embedding model: FORCED to jina-embeddings-v5-text-small ONLY (ingestion)
  • Reranker model selection (Jina Reranker v3 default)
  • Embedding dimension (1024 via Jina Matryoshka truncation)
  • Frontend CORS origin (configurable; default "*" for dev)
  • Logging level
  • LongText sliding window (now defaults to 30000 tokens via longtext_window_tokens)

Jina v5 only for embedding (per update request):
  • Model: jinaai/jina-embeddings-v5-text-small
  • Encode uses task="retrieval" (document/query prompt handled internally by Jina v5 ST model)
  • Re-ingest documents when model changes (vectors are model-specific).

Loaded from environment variables (or .env) at process start; never mutated at runtime.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ─── Model ids (Jina v5 embedding FORCED only; reranker still has choice) ─────
# Embedding is locked to Jina Embeddings v5 Text Small for all ingestion.

EMBEDDING_MODEL_IDS = {
    "jina-v5-small": "jina-embeddings-v5-text-small",
}
RERANKER_MODEL_IDS = {
    "jina-v3": "jina-reranker-v3",
    "bge-reranker-base": "bge-reranker-base",
}

# Native output dim for Jina v5 small.
MODEL_NATIVE_DIM = {
    "jina-v5-small": 1024,
}


class Settings(BaseSettings):
    """Application settings — bound to env vars with sensible v1.3 defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Neo4j ────────────────────────────────────────────────────────────────
    neo4j_uri: str = Field(default="bolt://localhost:7687", description="Neo4j bolt URI")
    neo4j_user: str = Field(default="neo4j")
    neo4j_password: str = Field(default="P@ssw0rd")
    neo4j_database: str = Field(default="neo4j", description="Target Neo4j database")
    neo4j_max_retries: int = Field(default=2, description="Max retries on transient Neo4j errors")

    # ─── Redis ────────────────────────────────────────────────────────────────
    redis_url: str = Field(default="redis://localhost:6379/0", description="Redis URL (job queue + progress)")

    # ─── Embedding model (FORCED Jina v5 small only) ──────────────────────────
    embedding_model: str = Field(
        default="jina-v5-small",
        description=(
            "Embedding model is FORCED to jina-embeddings-v5-text-small only. "
            "This value is locked for ingestion (task=\"retrieval\" conditioning)."
        ),
    )

    # ─── Reranker model selection (v1.3) ──────────────────────────────────────
    # Selectable logical id: "jina-v3" (default) | "bge-reranker-base".
    reranker_model: str = Field(
        default="jina-v3",
        description=(
            "Logical reranker model id. v1.3 default is jina-v3. "
            "Set RERANKER_MODEL=bge-reranker-base to use BGE-reranker-base."
        ),
    )

    # ─── HuggingFace repo ids (one per logical model id) ──────────────────────
    jina_v5_repo: str = Field(
        default="jinaai/jina-embeddings-v5-text-small",
        description="HuggingFace repo id for Jina Embeddings v5 Text Small (default embedding in v1.3)",
    )
    jina_reranker_repo: str = Field(
        default="jinaai/jina-reranker-v3",
        description="HuggingFace repo id for Jina Reranker v3 (default reranker in v1.3)",
    )
    bge_m3_repo: str = Field(
        default="BAAI/bge-m3",
        description="HuggingFace repo id for BGE-M3 (alternative embedding)",
    )
    bge_reranker_repo: str = Field(
        default="BAAI/bge-reranker-base",
        description="HuggingFace repo id for BGE-reranker-base (alternative reranker)",
    )

    # ─── Active model resolution helpers (derived from the logical ids above) ─
    # `embedding_model_name` and `reranker_model_name` are the LOCAL subdir names
    # under MODEL_PATH (e.g. /app/models/jina-embeddings-v5-text-small). They are
    # derived from the logical id so the operator only sets one env var.
    model_path: str = Field(
        default="/app/models",
        description="Root directory containing model snapshots (one subdir per repo)",
    )
    cuda_visible_devices: str = Field(default="0", description="Comma-separated GPU ids or -1 for CPU-only")
    embedding_dim: int = Field(
        default=1024,
        description=(
            "MUST be 1024. Jina v5 small (native 1024) is truncated via Matryoshka "
            "`truncate_dim` at model load to match the pre-set Neo4j vector index dim."
        ),
    )
    embedding_max_retries: int = Field(default=3, description="Per error-handling spec §3")
    embedding_batch_size: int = Field(default=16, description="Default encode batch size (reduced on CUDA OOM)")
    enable_reranker: bool = Field(default=True, description="Load the cross-encoder reranker on startup when available")

    # ─── Server / runtime ─────────────────────────────────────────────────────
    log_level: str = Field(default="INFO")
    frontend_origin: str = Field(
        default="*",
        description="Allowed CORS origin for the Next.js frontend (use a single origin in prod)",
    )
    job_poll_interval_ms: int = Field(default=1000, description="Suggested client poll interval (informational)")
    job_ttl_seconds: int = Field(default=86_400, description="Redis TTL for completed/failed job state")

    # ─── Chunking defaults (mirrors src/lib/rag/constants.ts) ─────────────────
    chunk_target_tokens_recursive: int = 512
    chunk_target_tokens_semantic: int = 400
    chunk_target_tokens_structure: int = 600
    chunk_overlap_tokens: int = 64
    longtext_window_tokens: int = 30000
    longtext_overlap_tokens: int = 3000

    # ─── Adaptive α/β sweep grid (construction note #2) ───────────────────────
    # alpha ∈ {0.1, 0.2, ..., 0.9}; beta = 1 - alpha.
    adaptive_alpha_grid: List[float] = Field(
        default_factory=lambda: [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    )

    # ─── Pagination ───────────────────────────────────────────────────────────
    default_page_size: int = 20
    max_page_size: int = 100

    # ─── Convenience flags ────────────────────────────────────────────────────
    @property
    def use_gpu(self) -> bool:
        """True when CUDA should be used (cuda_visible_devices != '-1' and torch sees a GPU)."""
        return self.cuda_visible_devices.strip() != "-1"

    @property
    def device(self) -> str:
        """Resolved torch device string ('cuda' or 'cpu')."""
        if not self.use_gpu:
            return "cpu"
        try:
            import torch  # local import — torch is optional at config load time

            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"

    @property
    def cors_origins(self) -> List[str]:
        """List of allowed CORS origins (parsed from frontend_origin)."""
        raw = self.frontend_origin.strip()
        if not raw or raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    # ─── v1.3 derived model attributes ────────────────────────────────────────

    @property
    def embedding_repo(self) -> str:
        """Always return Jina v5 small repo (embedding is forced to Jina only)."""
        return self.jina_v5_repo

    @property
    def reranker_repo(self) -> str:
        """Resolve the active reranker HuggingFace repo id from `reranker_model`."""
        if self.reranker_model == "bge-reranker-base":
            return self.bge_reranker_repo
        # Default to Jina v3 for "jina-v3" (and any unrecognized value).
        return self.jina_reranker_repo

    @property
    def embedding_model_name(self) -> str:
        """Local subdir name under MODEL_PATH for Jina v5 (forced)."""
        return "jina-embeddings-v5-text-small"

    @property
    def reranker_model_name(self) -> str:
        """Local subdir name under MODEL_PATH for the active reranker model.

        Derived from the logical id (e.g. "jina-v3" → "jina-reranker-v3").
        """
        return RERANKER_MODEL_IDS.get(self.reranker_model, "jina-reranker-v3")

    @property
    def model_dim(self) -> int:
        """Native output dimension of the (forced) Jina v5 small embedding model.

        Jina v5 small native = 1024. NOTE: ACTUAL stored vectors + Neo4j index
        use `embedding_dim` (1024) via Matryoshka `truncate_dim` at load time.
        """
        return MODEL_NATIVE_DIM.get(self.embedding_model, 1024)

    @property
    def reranker_max_length(self) -> int:
        """Max sequence length for the active reranker.

        Jina Reranker v3 supports 8192 tokens (long-context). BGE-reranker-base is 512.
        """
        if self.reranker_model == "bge-reranker-base":
            return 512
        return 8192  # jina-v3

    @field_validator("embedding_dim")
    @classmethod
    def _dim_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("embedding_dim must be positive (must be 1024 for jina-embeddings-v5-text-small + Neo4j index)")
        return v

    @field_validator("embedding_model")
    @classmethod
    def _embedding_model_must_be_known(cls, v: str) -> str:
        v_norm = (v or "").strip().lower()
        if v_norm != "jina-v5-small":
            # Force Jina v5 only for ingestion. Ignore other values but log intent.
            return "jina-v5-small"
        return v_norm

    @field_validator("reranker_model")
    @classmethod
    def _reranker_model_must_be_known(cls, v: str) -> str:
        v_norm = (v or "").strip().lower()
        if v_norm not in RERANKER_MODEL_IDS:
            raise ValueError(
                f"reranker_model must be one of {sorted(RERANKER_MODEL_IDS)} (got {v!r})"
            )
        return v_norm


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached Settings singleton."""
    return Settings()


# Module-level singleton for convenience imports.
settings = get_settings()
