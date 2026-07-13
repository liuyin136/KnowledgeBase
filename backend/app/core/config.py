from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    data_root: str = "/data"
    vault_root: str = "/data/rag/vault"
    vault_db_path: str = "/data/rag/vault.db"
    redis_url: str = "redis://redis:6379/0"
    rq_queue_name: str = "default"
    file_cache_ttl: int = 3600
    file_cache_max_bytes: int = 1_048_576
    frontend_origin: str = "*"
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "P@ssw0rd"
    default_coarse_dim: int = 256
    search_cache_ttl: int = 3600
    chunk_token_max: int = 29500
    embedding_dim: int = 1024
    rerank_n_ctx: int = 131072
    rerank_n_batch: int = 131072
    pending_rerank_ttl_sec: int = 1800
    episodic_memory_ttl_sec: int = 1800
    ingest_progress_ttl_sec: int = 1800
    otel_exporter_otlp_endpoint: str = ""
    otel_service_name: str = "knowledgebase-api"

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    data_root = os.environ.get("DATA_ROOT", "/data")
    return Settings(
        data_root=data_root,
        vault_root=os.environ.get("VAULT_ROOT", f"{data_root}/rag/vault"),
        vault_db_path=os.environ.get("VAULT_DB_PATH", f"{data_root}/rag/vault.db"),
        redis_url=os.environ.get("REDIS_URL", "redis://redis:6379/0"),
        rq_queue_name=os.environ.get("RQ_QUEUE_NAME", "default"),
        file_cache_ttl=int(os.environ.get("FILE_CACHE_TTL", "3600")),
        file_cache_max_bytes=int(os.environ.get("FILE_CACHE_MAX_BYTES", "1048576")),
        frontend_origin=os.environ.get("FRONTEND_ORIGIN", "*"),
        neo4j_uri=os.environ.get("NEO4J_URI", "bolt://neo4j:7687"),
        neo4j_user=os.environ.get("NEO4J_USER", "neo4j"),
        neo4j_password=os.environ.get("NEO4J_PASSWORD", "P@ssw0rd"),
        default_coarse_dim=int(os.environ.get("DEFAULT_COARSE_DIM", "256")),
        search_cache_ttl=int(os.environ.get("SEARCH_CACHE_TTL", "3600")),
        chunk_token_max=int(os.environ.get("CHUNK_TOKEN_MAX", "29500")),
        embedding_dim=int(os.environ.get("EMBEDDING_DIM", "1024")),
        rerank_n_ctx=int(os.environ.get("RERANK_N_CTX", "131072")),
        rerank_n_batch=int(os.environ.get("RERANK_N_BATCH", "131072")),
        pending_rerank_ttl_sec=int(os.environ.get("PENDING_RERANK_TTL_SEC", "1800")),
        episodic_memory_ttl_sec=int(os.environ.get("EPISODIC_MEMORY_TTL_SEC", "1800")),
        ingest_progress_ttl_sec=int(os.environ.get("INGEST_PROGRESS_TTL_SEC", "1800")),
        otel_exporter_otlp_endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", ""),
        otel_service_name=os.environ.get("OTEL_SERVICE_NAME", "knowledgebase-api"),
    )
