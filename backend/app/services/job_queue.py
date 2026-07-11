from __future__ import annotations

import redis
from rq import Queue

from app.core.config import get_settings
from app.services.ingest_status import set_pending
from app.services.ingest_guard import assert_ingestible_source

_redis: redis.Redis | None = None

INGEST_TASK = "app.workers.tasks.ingest_document"
INDEX_LOG_TASK = "app.workers.tasks.index_log_file"
HYBRID_SEARCH_FUSION_TASK = "app.workers.tasks.hybrid_search_fusion"
HYBRID_SEARCH_RERANK_TASK = "app.workers.tasks.hybrid_search_rerank"
# Backward-compatible alias for tests/scripts that still reference hybrid_search
HYBRID_SEARCH_TASK = HYBRID_SEARCH_FUSION_TASK


def get_redis_connection() -> redis.Redis:
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = redis.from_url(settings.redis_url)
    return _redis


def get_queue() -> Queue:
    settings = get_settings()
    queue_name = settings.rq_queue_name
    return Queue(queue_name, connection=get_redis_connection())


def enqueue_index_log(relative_path: str) -> str:
    job = get_queue().enqueue(INDEX_LOG_TASK, relative_path)
    return job.id


def enqueue_ingest_document(relative_path: str, *, traceparent: str = "") -> str:
    assert_ingestible_source(relative_path)
    job = get_queue().enqueue(
        INGEST_TASK,
        relative_path,
        traceparent,
        meta={"traceparent": traceparent, "task": "ingest_document"},
    )
    from app.services import ingest_progress

    ingest_progress.init_progress(job.id, active_phase="ast_split", relative_path=relative_path)
    set_pending(relative_path, job.id)
    return job.id


def enqueue_vault_ingest(file_id: str, *, traceparent: str = "") -> str:
    """Enqueue ingest for a vault file; set SQLite pending + lock before queue."""
    from app.services import vault_db

    row = vault_db.get_file_by_id(file_id)
    if not row or row["index_status"] == "deleted":
        raise ValueError(f"Vault file not found: {file_id}")
    if row.get("ingest_lock_job_id"):
        raise ValueError("File is locked while ingest is running")

    relative_path = row["relative_path"]
    job = get_queue().enqueue(
        INGEST_TASK,
        relative_path,
        traceparent,
        meta={"traceparent": traceparent, "vault_file_id": file_id, "task": "ingest_document"},
    )
    from app.services import ingest_progress

    ingest_progress.init_progress(job.id, active_phase="ast_split", relative_path=relative_path)
    vault_db.set_file_pending(relative_path, job.id)
    set_pending(relative_path, job.id)
    return job.id


def enqueue_hybrid_search(
    *,
    query: str,
    w1: float,
    w2: float,
    recall_k: int,
    rerank_k: int,
    coarse_dim: int,
    use_minmax_fallback: bool,
    traceparent: str,
    cache_key: str,
    span_id: str,
    allowed_paths: list[str] | None = None,
    scope_meta: dict | None = None,
) -> str:
    return enqueue_hybrid_search_fusion(
        query=query,
        w1=w1,
        w2=w2,
        recall_k=recall_k,
        rerank_k=rerank_k,
        coarse_dim=coarse_dim,
        use_minmax_fallback=use_minmax_fallback,
        traceparent=traceparent,
        cache_key=cache_key,
        span_id=span_id,
        allowed_paths=allowed_paths,
        scope_meta=scope_meta,
    )


def enqueue_hybrid_search_fusion(
    *,
    query: str,
    w1: float,
    w2: float,
    recall_k: int,
    rerank_k: int,
    coarse_dim: int,
    use_minmax_fallback: bool,
    traceparent: str,
    cache_key: str,
    span_id: str,
    allowed_paths: list[str] | None = None,
    scope_meta: dict | None = None,
) -> str:
    job = get_queue().enqueue(
        HYBRID_SEARCH_FUSION_TASK,
        query,
        w1,
        w2,
        recall_k,
        rerank_k,
        coarse_dim,
        traceparent,
        use_minmax_fallback,
        cache_key,
        span_id,
        allowed_paths,
        scope_meta,
        meta={"traceparent": traceparent, "span_id": span_id},
    )
    from app.services import search_progress

    search_progress.init_progress(
        job.id,
        active_phase="vault_scope" if allowed_paths is not None else "query_embed",
        span_id=span_id,
    )
    return job.id


def enqueue_hybrid_rerank(parent_job_id: str, *, traceparent: str = "") -> str:
    from app.services import pending_rerank, search_progress

    pending = pending_rerank.load_pending(parent_job_id)
    workflow_log = list((pending or {}).get("workflow_log") or [])
    span_id = (pending or {}).get("span_id")
    job = get_queue().enqueue(
        HYBRID_SEARCH_RERANK_TASK,
        parent_job_id,
        traceparent,
        meta={"traceparent": traceparent, "parent_job_id": parent_job_id},
        job_timeout=600,
    )
    search_progress.init_progress(
        job.id,
        active_phase="rerank",
        span_id=span_id,
        workflow_log=workflow_log,
    )
    return job.id
