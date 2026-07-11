"""RQ task functions executed by api-worker."""
from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np
from neo4j import GraphDatabase

from app.core.config import get_settings
from app.core.constants import GRANDCHILD_RERANK_TOKEN_LIMIT
from app.core.logging import configure_logging, get_logger
from app.models.neo4j_models import (
    Knowledge,
    KnowledgeChild,
    KnowledgeGrandchild,
    KnowledgeParent,
    node_to_dict,
)
from app.services import ingest_progress, jina_runtime, pending_rerank, retrieval_memory, search_cache, search_progress
from app.services.fusion import fuse_hybrid
from app.services.gpu_utils import get_vram_used_mb
from app.services.hierarchical_chunking import split_children, split_grandchildren, split_parents_ast
from app.services.ingest_status import set_error, set_indexed
from app.services.matryoshka import cosine_sim, matryoshka_truncate
from app.services.metrics import push_metrics
from app.services.neo4j_client import get_neo4j_client
from app.workers.health import check_health
from app.workers.otel import worker_trace

configure_logging(os.environ.get("OTEL_SERVICE_NAME", "knowledgebase-worker"))
logger = get_logger("rag.worker.tasks")


def _current_job_id() -> str:
    try:
        from rq import get_current_job

        job = get_current_job()
        if job:
            return job.id
    except Exception:
        pass
    return ""


def _current_vault_file_id() -> str | None:
    try:
        from rq import get_current_job

        job = get_current_job()
        if job and job.meta:
            fid = job.meta.get("vault_file_id")
            if fid:
                return str(fid)
    except Exception:
        pass
    return None


def _clear_vault_lock(
    relative_path: str,
    *,
    index_status: str,
    chunk_count: int | None = None,
    content_hash: str | None = None,
    error_message: str | None = None,
) -> None:
    from app.services import vault_db

    file_id = _current_vault_file_id()
    if file_id:
        vault_db.clear_file_lock_by_id(
            file_id,
            index_status=index_status,
            chunk_count=chunk_count,
            content_hash=content_hash,
            error_message=error_message,
        )
    else:
        vault_db.clear_file_lock(
            relative_path,
            index_status=index_status,
            chunk_count=chunk_count,
            content_hash=content_hash,
            error_message=error_message,
        )


def index_log_file(relative_path: str) -> dict[str, str | float | bool]:
    from app.services.ingest_guard import assert_ingestible_source

    assert_ingestible_source(relative_path)
    data_root = Path(os.environ.get("DATA_ROOT", "/data"))
    file_path = data_root / relative_path
    if not file_path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    parts = relative_path.split("/", 1)
    category = parts[0] if parts else "unknown"
    title = file_path.stem
    mtime = file_path.stat().st_mtime

    uri = os.environ.get("NEO4J_URI", "bolt://neo4j:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "P@ssw0rd")

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            session.run(
                """
                MERGE (f:LogFile {path: $path})
                SET f.category = $category,
                    f.title = $title,
                    f.mtime = $mtime
                """,
                path=relative_path,
                category=category,
                title=title,
                mtime=mtime,
            )
    finally:
        driver.close()

    return {"path": relative_path, "indexed": True}


def _publish_ingest_progress(
    job_id: str | None,
    workflow_log: list[dict[str, Any]],
    active_phase: str | None,
    relative_path: str | None = None,
) -> None:
    if not job_id:
        return
    ingest_progress.update_progress(
        job_id,
        workflow_log,
        active_phase,
        relative_path=relative_path,
    )


@check_health
@worker_trace("ingest_document")
def ingest_document(relative_path: str, traceparent: str = "") -> dict[str, Any]:
    from app.services.ingest_guard import assert_ingestible_source

    assert_ingestible_source(relative_path)
    job_id = _current_job_id()
    start = time.perf_counter()
    vram_peak_mb = 0
    mode = "legacy"
    workflow_log: list[dict[str, Any]] = []

    def _log_phase(entry: dict[str, Any]) -> None:
        workflow_log.append(entry)
        logger.info("ingest_phase", **entry)

    if job_id:
        ingest_progress.init_progress(
            job_id,
            active_phase="ast_split",
            relative_path=relative_path,
        )

    try:
        from app.services.vault_store import resolve_ingest_file
        from app.services.vault_sync import sync_vault_for_path
        from app.services import vault_db

        file_path, mode = resolve_ingest_file(relative_path)
        if not file_path.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")

        if mode == "vault":
            sync_vault_for_path(relative_path)
            if job_id:
                vault_db.set_file_pending(relative_path, job_id)

        text = file_path.read_text(encoding="utf-8")
        client = get_neo4j_client()

        knowledge_id = str(uuid.uuid4())
        existing_k = client.get_knowledge_by_source(relative_path)
        if existing_k and existing_k.get("id"):
            knowledge_id = existing_k["id"]

        _publish_ingest_progress(job_id, workflow_log, "ast_split", relative_path)
        t0 = time.perf_counter()
        parents_records = split_parents_ast(text)
        for parent in parents_records:
            parent.id = f"{knowledge_id}__p{parent.parent_index}"
        _log_phase(
            {
                "phase": "ast_split",
                "status": "done",
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "parent_count": len(parents_records),
            }
        )

        llm = jina_runtime.load_retrieval_model()
        try:
            tokenize, detokenize = jina_runtime.tokenizers_from_llm(llm)

            _publish_ingest_progress(job_id, workflow_log, "child_split", relative_path)
            t0 = time.perf_counter()
            children_records = []
            for parent in parents_records:
                children_records.extend(
                    split_children(parent, tokenize=tokenize, detokenize=detokenize)
                )
            _log_phase(
                {
                    "phase": "child_split",
                    "status": "done",
                    "latency_ms": int((time.perf_counter() - t0) * 1000),
                    "child_count": len(children_records),
                }
            )

            _publish_ingest_progress(job_id, workflow_log, "grandchild_split", relative_path)
            t0 = time.perf_counter()
            grandchildren_records = []
            for child in children_records:
                grandchildren_records.extend(split_grandchildren(child))
            _log_phase(
                {
                    "phase": "grandchild_split",
                    "status": "done",
                    "latency_ms": int((time.perf_counter() - t0) * 1000),
                    "grandchild_count": len(grandchildren_records),
                }
            )

            _publish_ingest_progress(job_id, workflow_log, "embed_children", relative_path)
            t0 = time.perf_counter()
            knowledge_children: list[KnowledgeChild] = []
            embedded_count = 0
            for child in children_records:
                full_vec = jina_runtime.embed_document(llm, child.content)
                coarse_256 = matryoshka_truncate(full_vec, 256).tolist()
                coarse_512 = matryoshka_truncate(full_vec, 512).tolist()
                vram_peak_mb = max(vram_peak_mb, get_vram_used_mb())
                embedded_count += 1

                knowledge_children.append(
                    KnowledgeChild(
                        id=child.id,
                        parent_id=child.parent_id,
                        child_index=child.child_index,
                        content=child.content,
                        content_hash=child.content_hash,
                        token_count=child.token_count,
                        source_file=relative_path,
                        vector=full_vec.tolist(),
                        vector_coarse_256=coarse_256,
                        vector_coarse_512=coarse_512,
                    )
                )
            _log_phase(
                {
                    "phase": "embed_children",
                    "status": "done",
                    "latency_ms": int((time.perf_counter() - t0) * 1000),
                    "embedded_count": embedded_count,
                }
            )
        finally:
            jina_runtime.release_model(llm)

        parts = relative_path.split("/", 1)
        knowledge = Knowledge(
            id=knowledge_id,
            source_file=relative_path,
            title=file_path.stem,
            category=parts[0] if parts else "",
            token_count=sum(c.token_count for c in children_records),
            chunk_count=len(children_records),
            last_content_hash=children_records[-1].content_hash if children_records else "",
            mtime=file_path.stat().st_mtime,
        )

        knowledge_parents = [
            KnowledgeParent(
                id=p.id,
                parent_index=p.parent_index,
                content=p.content,
                content_hash=p.content_hash,
                header_path=p.header_path,
                source_file=relative_path,
                token_count=p.token_count,
            )
            for p in parents_records
        ]
        knowledge_grandchildren = [
            KnowledgeGrandchild(
                id=g.id,
                child_id=g.child_id,
                parent_id=g.parent_id,
                grandchild_index=g.grandchild_index,
                content=g.content,
                source_file=relative_path,
            )
            for g in grandchildren_records
        ]

        _publish_ingest_progress(job_id, workflow_log, "neo4j_upsert", relative_path)
        t0 = time.perf_counter()
        client.delete_knowledge_tree_for_source(relative_path)
        stats = client.upsert_knowledge_tree(
            knowledge,
            knowledge_parents,
            knowledge_children,
            knowledge_grandchildren,
            skip_child_ids=set(),
            link_log_file=(mode != "vault"),
        )
        legacy_deleted = client.delete_legacy_chunks_for_source(relative_path)
        _log_phase(
            {
                "phase": "neo4j_upsert",
                "status": "done",
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "children_written": stats["children_written"],
                "children_skipped": stats["children_skipped"],
                "legacy_chunks_deleted": legacy_deleted,
            }
        )

        latency_ms = int((time.perf_counter() - start) * 1000)
        content_hash = knowledge.last_content_hash
        if mode == "vault":
            _clear_vault_lock(
                relative_path,
                index_status="indexed",
                chunk_count=len(children_records),
                content_hash=content_hash,
            )
        if job_id:
            set_indexed(relative_path, job_id, chunk_count=len(children_records))

        push_metrics(
            {
                "stage": "ingest_document",
                "latency_ms": latency_ms,
                "chunks_written": stats["children_written"],
                "chunks_skipped": stats["children_skipped"],
                "vram_peak_mb": vram_peak_mb,
            }
        )
        return {
            **stats,
            "parent_id": knowledge_id,
            "legacy_chunks_deleted": legacy_deleted,
            "vram_peak_mb": vram_peak_mb,
        }
    except Exception as exc:
        if mode == "vault":
            try:
                _clear_vault_lock(
                    relative_path,
                    index_status="error",
                    error_message=str(exc),
                )
            except Exception:
                pass
        if job_id:
            set_error(relative_path, job_id, str(exc))
        raise
    finally:
        if job_id:
            ingest_progress.clear_progress(job_id)


def _build_parent_paths(
    vector_hits: list[dict[str, Any]],
    bm25_hits: list[dict[str, Any]],
) -> dict[str, str]:
    parent_paths: dict[str, str] = {}
    for row in vector_hits + bm25_hits:
        child = node_to_dict(row["child"])
        cid = child["id"]
        source = str(child.get("source_file") or "")
        parent = row.get("parent")
        if parent is not None:
            source = str(node_to_dict(parent).get("source_file") or source)
        if source:
            from app.services.ingest_guard import is_blocked_source

            if not is_blocked_source(source):
                parent_paths[cid] = source
    return parent_paths


def _build_fusion_hits(
    fused: list[Any],
    pool: dict[str, dict[str, Any]],
    parent_paths: dict[str, str],
    *,
    rerank_by_idx: dict[int, float] | None = None,
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for i, hit in enumerate(fused):
        chunk = pool[hit.chunk_id]
        parent_path = parent_paths.get(hit.chunk_id, "")
        file_id = None
        index_status = None
        relative_path = parent_path or None
        if parent_path:
            try:
                from app.services import vault_db

                row = vault_db.get_file_by_path(parent_path)
                if row and row.get("index_status") != "deleted":
                    file_id = row["id"]
                    index_status = row["index_status"]
                    relative_path = row["relative_path"]
            except Exception:
                pass
        hit_dict: dict[str, Any] = {
            "chunk_id": hit.chunk_id,
            "child_id": hit.chunk_id,
            "parent_id": chunk.get("parent_id"),
            "parent_content": chunk.get("parent_content"),
            "header_path": chunk.get("header_path"),
            "parent_path": parent_path,
            "chunk_index": int(chunk.get("child_index", 0)),
            "content_preview": (chunk.get("content") or "")[:240],
            "final_score": hit.final_score,
            "display_score": hit.display_score,
            "file_id": file_id,
            "index_status": index_status,
            "relative_path": relative_path,
        }
        if rerank_by_idx is not None:
            hit_dict["rerank_score"] = float(rerank_by_idx.get(i, 0.0))
        else:
            hit_dict["rerank_score"] = None
        hits.append(hit_dict)
    return hits


def _publish_phase_progress(
    job_id: str | None,
    workflow_log: list[dict[str, Any]],
    active_phase: str | None,
    *,
    span_id: str | None = None,
) -> None:
    if not job_id:
        return
    search_progress.update_progress(job_id, workflow_log, active_phase, span_id=span_id)


def _assemble_parent_context(
    fused: list[Any],
    pool: dict[str, dict[str, Any]],
    client: Any,
) -> None:
    child_ids = [h.chunk_id for h in fused]
    parents = client.get_parents_by_child_ids(child_ids)
    for hit in fused:
        entry = pool[hit.chunk_id]
        parent_id = entry.get("parent_id")
        if not parent_id:
            continue
        pinfo = parents.get(parent_id)
        if not pinfo:
            continue
        entry["parent_content"] = pinfo.get("content") or ""
        entry["header_path"] = pinfo.get("header_path") or ""
        if pinfo.get("source_file"):
            entry["source_file"] = pinfo["source_file"]


def _apply_grandchild_rerank_if_fit(
    query: str,
    fused: list[Any],
    pool: dict[str, dict[str, Any]],
    client: Any,
) -> list[Any]:
    if not fused:
        return fused

    top_n = min(5, len(fused))
    top_hits = fused[:top_n]
    child_ids = [h.chunk_id for h in top_hits]
    grandchildren = client.get_grandchildren_for_children(child_ids)
    if not grandchildren:
        return fused

    for row in grandchildren:
        cid = row["child_id"]
        if cid in pool:
            pool[cid].setdefault("grandchild_ids", []).append(row["id"])

    docs = [str(row.get("content") or "") for row in grandchildren]
    token_count = jina_runtime.estimate_rerank_prompt_tokens(query, docs)
    if token_count > GRANDCHILD_RERANK_TOKEN_LIMIT:
        logger.info(
            "grandchild_rerank_skipped",
            token_count=token_count,
            limit=GRANDCHILD_RERANK_TOKEN_LIMIT,
        )
        return fused

    reranker = jina_runtime.load_reranker()
    try:
        reranked = jina_runtime.rerank_documents(reranker, query, docs, top_n=len(docs))
    finally:
        jina_runtime.release_reranker(reranker)

    gc_child_map = [row["child_id"] for row in grandchildren]
    child_scores: dict[str, float] = {}
    for result in reranked:
        if result.index >= len(gc_child_map):
            continue
        cid = gc_child_map[result.index]
        score = float(result.relevance_score)
        child_scores[cid] = max(child_scores.get(cid, 0.0), score)

    reordered_top = sorted(
        top_hits,
        key=lambda h: child_scores.get(h.chunk_id, 0.0),
        reverse=True,
    )
    return reordered_top + fused[top_n:]


def _parent_rerank_inputs(
    fused: list[Any],
    pool: dict[str, dict[str, Any]],
) -> list[str]:
    seen_parent_ids: set[str] = set()
    rerank_inputs: list[str] = []
    for hit in fused:
        entry = pool[hit.chunk_id]
        parent_id = entry.get("parent_id")
        if not parent_id or parent_id in seen_parent_ids:
            continue
        parent_content = str(entry.get("parent_content") or "").strip()
        if not parent_content:
            continue
        seen_parent_ids.add(parent_id)
        rerank_inputs.append(parent_content)
    return rerank_inputs


def _retrieval_tree_from_fused(
    fused: list[Any],
    pool: dict[str, dict[str, Any]],
) -> dict[str, list[str]]:
    parent_ids: list[str] = []
    child_ids: list[str] = []
    grandchild_ids: list[str] = []
    for hit in fused:
        entry = pool[hit.chunk_id]
        parent_id = entry.get("parent_id")
        if parent_id:
            parent_ids.append(str(parent_id))
        child_ids.append(hit.chunk_id)
        grandchild_ids.extend(entry.get("grandchild_ids") or [])
    return {
        "parent_ids": list(dict.fromkeys(parent_ids)),
        "child_ids": list(dict.fromkeys(child_ids)),
        "grandchild_ids": list(dict.fromkeys(grandchild_ids)),
    }


def _hybrid_recall_and_fusion(
    query: str,
    w1: float,
    w2: float,
    recall_k: int,
    rerank_k: int,
    coarse_dim: int,
    *,
    use_minmax_fallback: bool = False,
    allowed_paths: list[str] | None = None,
    scope_meta: dict | None = None,
    job_id: str | None = None,
    span_id: str | None = None,
) -> dict[str, Any]:
    client = get_neo4j_client()
    workflow_log: list[dict[str, Any]] = []
    vram_peak_mb = 0
    scope_meta = scope_meta or {}

    def _log_phase(entry: dict[str, Any]) -> None:
        workflow_log.append(entry)
        logger.info("search_phase", **entry)

    if allowed_paths is not None:
        _publish_phase_progress(job_id, workflow_log, "vault_scope", span_id=span_id)
        t0 = time.perf_counter()
        _log_phase(
            {
                "phase": "vault_scope",
                "status": "done",
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "hit_count": len(allowed_paths),
            }
        )
        _publish_phase_progress(job_id, workflow_log, "query_embed", span_id=span_id)
        if len(allowed_paths) == 0:
            return {
                "empty_scope": True,
                "workflow_log": workflow_log,
                "pool": {},
                "fused": [],
                "rerank_inputs": [],
                "vector_hits": [],
                "bm25_hits": [],
                "parent_paths": {},
                "vram_peak_mb": vram_peak_mb,
            }

    _publish_phase_progress(job_id, workflow_log, "query_embed", span_id=span_id)
    t0 = time.perf_counter()
    llm = jina_runtime.load_retrieval_model()
    try:
        q_full = jina_runtime.embed_query(llm, query)
        vram_peak_mb = max(vram_peak_mb, get_vram_used_mb())
    finally:
        jina_runtime.release_model(llm)
    _log_phase(
        {
            "phase": "query_embed",
            "status": "done",
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "model": "jina-retrieval",
            "vram_peak_mb": vram_peak_mb,
        }
    )
    _publish_phase_progress(job_id, workflow_log, "coarse_ann", span_id=span_id)

    q_coarse = matryoshka_truncate(q_full, coarse_dim)

    t0 = time.perf_counter()
    vector_hits = client.vector_search_coarse_children(
        coarse_dim, q_coarse.tolist(), recall_k, allowed_paths=allowed_paths
    )
    _log_phase(
        {
            "phase": "coarse_ann",
            "status": "done",
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "hit_count": len(vector_hits),
            "coarse_dim": coarse_dim,
        }
    )
    _publish_phase_progress(job_id, workflow_log, "bm25_recall", span_id=span_id)

    t0 = time.perf_counter()
    bm25_hits = client.bm25_search_children(query, recall_k, allowed_paths=allowed_paths)
    _log_phase(
        {
            "phase": "bm25_recall",
            "status": "done",
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "hit_count": len(bm25_hits),
        }
    )
    _publish_phase_progress(job_id, workflow_log, "rescore_1024", span_id=span_id)

    pool: dict[str, dict[str, Any]] = {}
    vector_scores: dict[str, float] = {}
    bm25_scores: dict[str, float] = {}

    for row in vector_hits:
        child = node_to_dict(row["child"])
        cid = child["id"]
        parent = node_to_dict(row.get("parent"))
        pool[cid] = {
            "id": cid,
            "parent_id": parent.get("id") or child.get("parent_id"),
            "child_index": int(child.get("child_index", 0)),
            "content": child.get("content") or "",
        }
        vector_scores[cid] = float(row.get("vector_score") or 0.0)

    for row in bm25_hits:
        child = node_to_dict(row["child"])
        cid = child["id"]
        parent = node_to_dict(row.get("parent"))
        pool[cid] = {
            "id": cid,
            "parent_id": parent.get("id") or child.get("parent_id"),
            "child_index": int(child.get("child_index", 0)),
            "content": child.get("content") or "",
        }
        bm25_scores[cid] = float(row.get("bm25_score") or 0.0)

    t0 = time.perf_counter()
    child_meta = client.get_child_vectors(list(pool.keys()))
    for cid, meta in child_meta.items():
        vec = np.asarray(meta["vector"], dtype=np.float32)
        vector_scores[cid] = cosine_sim(q_full, vec)
        if cid in pool:
            pool[cid]["parent_id"] = meta.get("parent_id") or pool[cid].get("parent_id")
    _log_phase(
        {
            "phase": "rescore_1024",
            "status": "done",
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "pool_size": len(pool),
            "rescore_dim": 1024,
        }
    )
    _publish_phase_progress(job_id, workflow_log, "hybrid_fusion", span_id=span_id)

    t0 = time.perf_counter()
    fused = fuse_hybrid(
        list(pool.keys()),
        vector_scores,
        bm25_scores,
        w1=w1,
        w2=w2,
        use_minmax_fallback=use_minmax_fallback,
    )[:rerank_k]
    _log_phase(
        {
            "phase": "hybrid_fusion",
            "status": "done",
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "w1": w1,
            "w2": w2,
            "pool_size": len(pool),
            "rerank_k": rerank_k,
        }
    )

    fused = _apply_grandchild_rerank_if_fit(query, fused, pool, client)
    _assemble_parent_context(fused, pool, client)
    rerank_inputs = _parent_rerank_inputs(fused, pool)
    parent_paths = _build_parent_paths(vector_hits, bm25_hits)
    _publish_phase_progress(job_id, workflow_log, None, span_id=span_id)

    return {
        "empty_scope": False,
        "workflow_log": workflow_log,
        "pool": pool,
        "fused": fused,
        "rerank_inputs": rerank_inputs,
        "vector_hits": vector_hits,
        "bm25_hits": bm25_hits,
        "parent_paths": parent_paths,
        "vram_peak_mb": vram_peak_mb,
    }


def _fusion_meta_from_parts(
    *,
    pool_size: int,
    w1: float,
    w2: float,
    recall_k: int,
    rerank_k: int,
    coarse_dim: int,
    latency_ms: int,
    vector_hit_count: int,
    bm25_hit_count: int,
    vram_peak_mb: int,
    allowed_paths: list[str] | None,
    scope_meta: dict[str, Any],
) -> dict[str, Any]:
    fusion_meta: dict[str, Any] = {
        "pool_size": pool_size,
        "w1": w1,
        "w2": w2,
        "recall_k": recall_k,
        "rerank_k": rerank_k,
        "coarse_dim": coarse_dim,
        "rescore_dim": 1024,
        "latency_ms": latency_ms,
        "vector_hit_count": vector_hit_count,
        "bm25_hit_count": bm25_hit_count,
        "vram_peak_mb": vram_peak_mb,
    }
    if allowed_paths is not None:
        fusion_meta["allowlist_size"] = len(allowed_paths)
        for key in ("folder_ids", "created_after", "created_before", "indexed_only"):
            if key in scope_meta:
                fusion_meta[key] = scope_meta[key]
    return fusion_meta


def _slim_pool_for_pending(pool: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Keep only rerank-rebuild fields; Neo4j DateTime/vectors are not JSON-serializable."""
    slim: dict[str, dict[str, Any]] = {}
    for cid, chunk in pool.items():
        slim[cid] = {
            "id": cid,
            "parent_id": chunk.get("parent_id"),
            "child_index": int(chunk.get("child_index", 0)),
            "content": str(chunk.get("content") or ""),
            "parent_content": str(chunk.get("parent_content") or ""),
        }
    return slim


@check_health
@worker_trace("hybrid_search_fusion")
def hybrid_search_fusion(
    query: str,
    w1: float,
    w2: float,
    recall_k: int,
    rerank_k: int,
    coarse_dim: int,
    traceparent: str = "",
    use_minmax_fallback: bool = False,
    cache_key: str | None = None,
    span_id: str | None = None,
    allowed_paths: list[str] | None = None,
    scope_meta: dict | None = None,
) -> dict[str, Any]:
    start = time.perf_counter()
    scope_meta = scope_meta or {}
    settings = get_settings()
    job_id = _current_job_id()
    resolved_span_id = span_id or uuid.uuid4().hex[:16]

    try:
        fusion_data = _hybrid_recall_and_fusion(
            query,
            w1,
            w2,
            recall_k,
            rerank_k,
            coarse_dim,
            use_minmax_fallback=use_minmax_fallback,
            allowed_paths=allowed_paths,
            scope_meta=scope_meta,
            job_id=job_id,
            span_id=resolved_span_id,
        )
        workflow_log = fusion_data["workflow_log"]
        vram_peak_mb = fusion_data["vram_peak_mb"]

        if fusion_data.get("empty_scope"):
            latency_ms = int((time.perf_counter() - start) * 1000)
            fusion_meta = _fusion_meta_from_parts(
                pool_size=0,
                w1=w1,
                w2=w2,
                recall_k=recall_k,
                rerank_k=rerank_k,
                coarse_dim=coarse_dim,
                latency_ms=latency_ms,
                vector_hit_count=0,
                bm25_hit_count=0,
                vram_peak_mb=vram_peak_mb,
                allowed_paths=allowed_paths,
                scope_meta=scope_meta,
            )
            return {
                "status": "finished",
                "hits": [],
                "fusion_meta": fusion_meta,
                "workflow_log": workflow_log,
                "span_id": resolved_span_id,
            }

        pool = fusion_data["pool"]
        fused = fusion_data["fused"]
        rerank_inputs = fusion_data["rerank_inputs"]
        parent_paths = fusion_data["parent_paths"]
        vector_hits = fusion_data["vector_hits"]
        bm25_hits = fusion_data["bm25_hits"]
        retrieval_tree = _retrieval_tree_from_fused(fused, pool)

        rerank_token_count = jina_runtime.estimate_rerank_prompt_tokens(query, rerank_inputs)
        hits_fusion = _build_fusion_hits(fused, pool, parent_paths, rerank_by_idx=None)

        latency_ms = int((time.perf_counter() - start) * 1000)
        fusion_meta = _fusion_meta_from_parts(
            pool_size=len(pool),
            w1=w1,
            w2=w2,
            recall_k=recall_k,
            rerank_k=rerank_k,
            coarse_dim=coarse_dim,
            latency_ms=latency_ms,
            vector_hit_count=len(vector_hits),
            bm25_hit_count=len(bm25_hits),
            vram_peak_mb=vram_peak_mb,
            allowed_paths=allowed_paths,
            scope_meta=scope_meta,
        )

        if job_id:
            slim_pool = _slim_pool_for_pending(pool)
            pending_payload = {
                "query": query,
                "rerank_inputs": rerank_inputs,
                "fused_chunk_ids": [h.chunk_id for h in fused],
                "rerank_k": rerank_k,
                "cache_key": cache_key,
                "span_id": resolved_span_id,
                "scope_meta": scope_meta,
                "fusion_meta": fusion_meta,
                "workflow_log": workflow_log,
                "hits_fusion": hits_fusion,
                "pool": slim_pool,
                "fused": [
                    {
                        "chunk_id": h.chunk_id,
                        "final_score": h.final_score,
                        "display_score": h.display_score,
                    }
                    for h in fused
                ],
                "parent_paths": parent_paths,
                "retrieval_tree": retrieval_tree,
                # jobs.confirm_rerank skip path should call retrieval_memory.save_retrieval_tree
                "w1": w1,
                "w2": w2,
                "recall_k": recall_k,
                "coarse_dim": coarse_dim,
                "allowed_paths": allowed_paths,
            }
            pending_rerank.save_pending(job_id, pending_payload)

        push_metrics(
            {
                "stage": "hybrid_search_fusion",
                "latency_ms": latency_ms,
                "retrieval_k": recall_k,
                "candidate_count": len(pool),
                "vector_hit_count": len(vector_hits),
                "bm25_hit_count": len(bm25_hits),
                "vram_peak_mb": vram_peak_mb,
                "rerank_token_count": rerank_token_count,
            }
        )

        return {
            "status": "awaiting_rerank",
            "rerank_token_count": rerank_token_count,
            "rerank_ctx_limit": settings.rerank_n_ctx,
            "rerank_doc_count": len(rerank_inputs),
            "hits": hits_fusion,
            "fusion_meta": fusion_meta,
            "workflow_log": workflow_log,
            "span_id": resolved_span_id,
        }
    finally:
        if job_id:
            search_progress.clear_progress(job_id)


@check_health
@worker_trace("hybrid_search_rerank")
def hybrid_search_rerank(parent_job_id: str, traceparent: str = "") -> dict[str, Any]:
    start = time.perf_counter()
    job_id = _current_job_id()
    pending = pending_rerank.load_pending(parent_job_id)
    if pending is None:
        raise ValueError(f"Pending rerank session expired or not found: {parent_job_id}")

    query = pending["query"]
    rerank_inputs = pending["rerank_inputs"]
    rerank_k = int(pending["rerank_k"])
    cache_key = pending.get("cache_key")
    span_id = pending.get("span_id") or uuid.uuid4().hex[:16]
    workflow_log = list(pending.get("workflow_log") or [])
    fusion_meta = dict(pending.get("fusion_meta") or {})
    pool = pending["pool"]
    fused_raw = pending["fused"]
    parent_paths = pending.get("parent_paths") or {}

    from app.services.fusion import FusionHit

    fused = [
        FusionHit(
            chunk_id=item["chunk_id"],
            final_score=float(item["final_score"]),
            display_score=float(item["display_score"]),
            vector_score=0.0,
            bm25_score=0.0,
        )
        for item in fused_raw
    ]

    vram_peak_mb = int(fusion_meta.get("vram_peak_mb") or 0)

    try:
        _publish_phase_progress(job_id, workflow_log, "rerank", span_id=span_id)
        t0 = time.perf_counter()
        reranker = jina_runtime.load_reranker()
        try:
            reranked = jina_runtime.rerank_documents(reranker, query, rerank_inputs, rerank_k)
            vram_peak_mb = max(vram_peak_mb, get_vram_used_mb())
        finally:
            jina_runtime.release_reranker(reranker)

        rerank_by_idx = {r.index: r.relevance_score for r in reranked}
        workflow_log.append(
            {
                "phase": "rerank",
                "status": "done",
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "model": "jina-reranker",
                "vram_peak_mb": vram_peak_mb,
                "rerank_k": rerank_k,
            }
        )
        _publish_phase_progress(job_id, workflow_log, None, span_id=span_id)

        hits = _build_fusion_hits(fused, pool, parent_paths, rerank_by_idx=rerank_by_idx)
        hits.sort(key=lambda h: h.get("rerank_score") or 0.0, reverse=True)

        latency_ms = int((time.perf_counter() - start) * 1000)
        fusion_meta["latency_ms"] = int(fusion_meta.get("latency_ms", 0)) + latency_ms
        fusion_meta["vram_peak_mb"] = vram_peak_mb

        result = {
            "status": "finished",
            "hits": hits,
            "fusion_meta": fusion_meta,
            "workflow_log": workflow_log,
            "span_id": span_id,
        }
        if cache_key:
            search_cache.set_cached(cache_key, result)

        tree = pending.get("retrieval_tree") or {}
        if tree:
            retrieval_memory.save_retrieval_tree(
                parent_job_id,
                parent_ids=tree.get("parent_ids") or [],
                child_ids=tree.get("child_ids") or [],
                grandchild_ids=tree.get("grandchild_ids") or [],
                span_id=span_id,
                query=query,
            )

        pending_rerank.delete_pending(parent_job_id)

        push_metrics(
            {
                "stage": "hybrid_search_rerank",
                "latency_ms": latency_ms,
                "rerank_k": rerank_k,
                "vram_peak_mb": vram_peak_mb,
            }
        )

        return result
    finally:
        if job_id:
            search_progress.clear_progress(job_id)


@check_health
@worker_trace("hybrid_search")
def hybrid_search(
    query: str,
    w1: float,
    w2: float,
    recall_k: int,
    rerank_k: int,
    coarse_dim: int,
    traceparent: str = "",
    use_minmax_fallback: bool = False,
    cache_key: str | None = None,
    span_id: str | None = None,
    allowed_paths: list[str] | None = None,
    scope_meta: dict | None = None,
) -> dict[str, Any]:
    """Backward-compatible alias: fusion-only (awaiting user-confirmed rerank)."""
    return hybrid_search_fusion(
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
    )
