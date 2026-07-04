"""
core/config.py — Pydantic Settings for the Local-First RAG Experimentation Platform v1.2.

All environment-driven configuration lives here. Single source of truth for:
  • Neo4j connection (URI/user/password) — per infrastructure-environment-spec_v1.1.md §5
  • Redis URL (job queue + progress tracking)
  • Embedding model path + device (BGE-M3 on GPU when available)
  • Embedding dimension (1024 for BGE-M3, per neo4j-schema-v1.1.md §3)
  • Frontend CORS origin (configurable; default "*" for dev)
  • Logging level

Loaded from environment variables (or .env) at process start; never mutated at runtime.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings — bound to env vars with sensible v1.2 defaults."""

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

    # ─── Embedding model (BGE-M3) ─────────────────────────────────────────────
    model_path: str = Field(
        default="/app/models",
        description="Root directory containing BGE-M3 (and optional reranker) snapshots",
    )
    bge_m3_repo: str = Field(default="BAAI/bge-m3", description="HuggingFace repo id for the embedding model")
    bge_reranker_repo: str = Field(
        default="BAAI/bge-reranker-base",
        description="HuggingFace repo id for the optional cross-encoder reranker",
    )
    embedding_model_name: str = Field(default="bge-m3", description="Local subdir name under MODEL_PATH")
    reranker_model_name: str = Field(default="bge-reranker-base", description="Local subdir name under MODEL_PATH")
    cuda_visible_devices: str = Field(default="0", description="Comma-separated GPU ids or -1 for CPU-only")
    embedding_dim: int = Field(default=1024, description="BGE-M3 output dimension (matches neo4j-schema §3)")
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
    longtext_window_tokens: int = 8000
    longtext_overlap_tokens: int = 800

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

    @field_validator("embedding_dim")
    @classmethod
    def _dim_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("embedding_dim must be positive (BGE-M3 = 1024)")
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached Settings singleton."""
    return Settings()


# Module-level singleton for convenience imports.
settings = get_settings()
