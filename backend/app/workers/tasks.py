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
from app.core.constants import GRANDCHILD_RERANK_TOKEN_LIMIT, TIER_RECALL_K
from app.core.logging import configure_logging, get_logger
from app.models.neo4j_models import (
    Knowledge,
    KnowledgeChild,
    KnowledgeFamily,
    KnowledgeGrandchild,
    KnowledgeParent,
    node_to_dict,
)
from app.services import ingest_progress, jina_runtime, pending_rerank, retrieval_memory, search_cache, search_progress
from app.services.fusion import fuse_hybrid
from app.services.gpu_utils import get_vram_used_mb
from app.services.hierarchical_chunking import build_hierarchical_tree
from app.services.hierarchical_fusion import (
    HierarchicalHit,
    aggregate_hierarchical_scores,
    fuse_tier_pool,
)
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

    def _embed_text(llm: Any, content: str) -> tuple[list[float], list[float], list[float]]:
        nonlocal vram_peak_mb
        full_vec = jina_runtime.embed_document(llm, content)
        coarse_256 = matryoshka_truncate(full_vec, 256).tolist()
        coarse_512 = matryoshka_truncate(full_vec, 512).tolist()
        vram_peak_mb = max(vram_peak_mb, get_vram_used_mb())
        return full_vec.tolist(), coarse_256, coarse_512

    if job_id:
        ingest_progress.init_progress(
            job_id,
            active_phase="front_matter",
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

        llm = jina_runtime.load_retrieval_model()
        try:
            tokenize, detokenize = jina_runtime.tokenizers_from_llm(llm)

            _publish_ingest_progress(job_id, workflow_log, "front_matter", relative_path)
            t0 = time.perf_counter()
            tree = build_hierarchical_tree(text, tokenize=tokenize, detokenize=detokenize)
            _log_phase(
                {
                    "phase": "front_matter",
                    "status": "done",
                    "latency_ms": int((time.perf_counter() - t0) * 1000),
                    "family_count": 1 if tree.front_matter.fields or tree.front_matter.raw_yaml else 0,
                }
            )

            if mode == "vault":
                file_row = vault_db.get_file_by_path(relative_path)
                if file_row:
                    vault_db.upsert_doc_meta(
                        file_row["id"],
                        raw_yaml=tree.front_matter.raw_yaml,
                        fields=tree.front_matter.fields,
                    )

            # Assign stable IDs under knowledge_id
            for fam in tree.families:
                fam.id = f"{knowledge_id}__f{fam.family_index}"
            for parent in tree.parents:
                parent.id = f"{knowledge_id}__p{parent.parent_index}"
                parent.family_id = next(
                    (f.id for f in tree.families if f.family_index == parent.family_index),
                    tree.families[0].id if tree.families else "",
                )
            # Rebuild children/grandchildren IDs after parent id rewrite
            for child in tree.children:
                parent = next((p for p in tree.parents if p.parent_index == child.parent_index), None)
                if parent:
                    child.parent_id = parent.id
                    child.family_id = parent.family_id
                child.id = f"{child.parent_id}__c{child.child_index}"
            for g in tree.grandchildren:
                child = next(
                    (
                        c
                        for c in tree.children
                        if c.child_index == g.child_index and c.parent_index == g.parent_index
                    ),
                    None,
                )
                if child:
                    g.child_id = child.id
                    g.parent_id = child.parent_id
                g.id = f"{g.parent_id}__c{g.child_index}__g{g.grandchild_index}"

            _publish_ingest_progress(job_id, workflow_log, "family_split", relative_path)
            t0 = time.perf_counter()
            _log_phase(
                {
                    "phase": "family_split",
                    "status": "done",
                    "latency_ms": int((time.perf_counter() - t0) * 1000),
                    "family_count": len(tree.families),
                }
            )

            _publish_ingest_progress(job_id, workflow_log, "parent_split", relative_path)
            t0 = time.perf_counter()
            _log_phase(
                {
                    "phase": "parent_split",
                    "status": "done",
                    "latency_ms": int((time.perf_counter() - t0) * 1000),
                    "parent_count": len(tree.parents),
                }
            )

            _publish_ingest_progress(job_id, workflow_log, "child_split", relative_path)
            t0 = time.perf_counter()
            _log_phase(
                {
                    "phase": "child_split",
                    "status": "done",
                    "latency_ms": int((time.perf_counter() - t0) * 1000),
                    "child_count": len(tree.children),
                }
            )

            _publish_ingest_progress(job_id, workflow_log, "grandchild_split", relative_path)
            t0 = time.perf_counter()
            _log_phase(
                {
                    "phase": "grandchild_split",
                    "status": "done",
                    "latency_ms": int((time.perf_counter() - t0) * 1000),
                    "grandchild_count": len(tree.grandchildren),
                }
            )

            _publish_ingest_progress(job_id, workflow_log, "embed_family", relative_path)
            t0 = time.perf_counter()
            knowledge_families: list[KnowledgeFamily] = []
            for fam in tree.families:
                vec, c256, c512 = _embed_text(llm, fam.content)
                knowledge_families.append(
                    KnowledgeFamily(
                        id=fam.id,
                        family_index=fam.family_index,
                        content=fam.content,
                        content_hash=fam.content_hash,
                        source_file=relative_path,
                        token_count=fam.token_count,
                        vector=vec,
                        vector_coarse_256=c256,
                        vector_coarse_512=c512,
                    )
                )
            _log_phase(
                {
                    "phase": "embed_family",
                    "status": "done",
                    "latency_ms": int((time.perf_counter() - t0) * 1000),
                    "embedded_count": len(knowledge_families),
                }
            )

            _publish_ingest_progress(job_id, workflow_log, "embed_parent", relative_path)
            t0 = time.perf_counter()
            knowledge_parents: list[KnowledgeParent] = []
            for p in tree.parents:
                vec, c256, c512 = _embed_text(llm, p.content)
                knowledge_parents.append(
                    KnowledgeParent(
                        id=p.id,
                        parent_index=p.parent_index,
                        content=p.content,
                        content_hash=p.content_hash,
                        header_path=p.header_path,
                        source_file=relative_path,
                        token_count=p.token_count,
                        family_id=p.family_id,
                        vector=vec,
                        vector_coarse_256=c256,
                        vector_coarse_512=c512,
                    )
                )
            _log_phase(
                {
                    "phase": "embed_parent",
                    "status": "done",
                    "latency_ms": int((time.perf_counter() - t0) * 1000),
                    "embedded_count": len(knowledge_parents),
                }
            )

            _publish_ingest_progress(job_id, workflow_log, "embed_child", relative_path)
            t0 = time.perf_counter()
            knowledge_children: list[KnowledgeChild] = []
            for child in tree.children:
                vec, c256, c512 = _embed_text(llm, child.content)
                knowledge_children.append(
                    KnowledgeChild(
                        id=child.id,
                        parent_id=child.parent_id,
                        child_index=child.child_index,
                        content=child.content,
                        content_hash=child.content_hash,
                        token_count=child.token_count,
                        source_file=relative_path,
                        block_type=child.block_type,
                        vector=vec,
                        vector_coarse_256=c256,
                        vector_coarse_512=c512,
                    )
                )
            _log_phase(
                {
                    "phase": "embed_child",
                    "status": "done",
                    "latency_ms": int((time.perf_counter() - t0) * 1000),
                    "embedded_count": len(knowledge_children),
                }
            )

            _publish_ingest_progress(job_id, workflow_log, "embed_grandchild", relative_path)
            t0 = time.perf_counter()
            knowledge_grandchildren: list[KnowledgeGrandchild] = []
            for g in tree.grandchildren:
                vec, c256, c512 = _embed_text(llm, g.content)
                knowledge_grandchildren.append(
                    KnowledgeGrandchild(
                        id=g.id,
                        child_id=g.child_id,
                        parent_id=g.parent_id,
                        grandchild_index=g.grandchild_index,
                        content=g.content,
                        source_file=relative_path,
                        content_hash=g.content_hash,
                        token_count=g.token_count,
                        vector=vec,
                        vector_coarse_256=c256,
                        vector_coarse_512=c512,
                    )
                )
            _log_phase(
                {
                    "phase": "embed_grandchild",
                    "status": "done",
                    "latency_ms": int((time.perf_counter() - t0) * 1000),
                    "embedded_count": len(knowledge_grandchildren),
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
            token_count=sum(c.token_count for c in knowledge_children),
            chunk_count=len(knowledge_children),
            last_content_hash=knowledge_children[-1].content_hash if knowledge_children else "",
            mtime=file_path.stat().st_mtime,
        )

        _publish_ingest_progress(job_id, workflow_log, "neo4j_upsert", relative_path)
        t0 = time.perf_counter()
        stats = client.upsert_knowledge_tree_v162(
            knowledge,
            knowledge_families,
            knowledge_parents,
            knowledge_children,
            knowledge_grandchildren,
            link_log_file=(mode != "vault"),
        )
        legacy_deleted = client.delete_legacy_chunks_for_source(relative_path)
        _log_phase(
            {
                "phase": "neo4j_upsert",
                "status": "done",
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "children_written": stats["children_written"],
                "family_count": stats["families_written"],
                "parent_count": stats["parents_written"],
                "grandchild_count": stats["grandchildren_written"],
            }
        )
        _publish_ingest_progress(job_id, workflow_log, None, relative_path)

        latency_ms = int((time.perf_counter() - start) * 1000)
        content_hash = knowledge.last_content_hash
        if mode == "vault":
            _clear_vault_lock(
                relative_path,
                index_status="indexed",
                chunk_count=len(knowledge_children),
                content_hash=content_hash,
            )
        if job_id:
            set_indexed(relative_path, job_id, chunk_count=len(knowledge_children))

        push_metrics(
            {
                "stage": "ingest_document",
                "latency_ms": latency_ms,
                "chunks_written": stats["children_written"],
                "vram_peak_mb": vram_peak_mb,
            }
        )
        return {
            **stats,
            "parent_id": knowledge_id,
            "legacy_chunks_deleted": legacy_deleted,
            "vram_peak_mb": vram_peak_mb,
            "workflow_log": workflow_log,
            "relative_path": relative_path,
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
        if isinstance(hit, HierarchicalHit):
            chunk_id = hit.grandchild_id
            entry = pool.get(chunk_id) or {
                "parent_id": hit.parent_id,
                "child_id": hit.child_id,
                "family_id": hit.family_id,
                "child_index": hit.child_index,
                "content": hit.content,
                "parent_content": hit.parent_content,
                "header_path": hit.header_path,
                "source_file": hit.source_file,
            }
            parent_path = parent_paths.get(chunk_id) or hit.source_file or ""
            vector_score = hit.vector_score
            final_score = hit.final_score
            display_score = hit.display_score
            child_id = hit.child_id
            parent_id = hit.parent_id
            family_id = hit.family_id
        else:
            chunk_id = hit.chunk_id
            entry = pool[chunk_id]
            parent_path = parent_paths.get(chunk_id, "")
            vector_score = float(getattr(hit, "vector_score", 0.0) or 0.0)
            final_score = hit.final_score
            display_score = hit.display_score
            child_id = chunk_id
            parent_id = entry.get("parent_id")
            family_id = entry.get("family_id")

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
            "chunk_id": chunk_id,
            "child_id": child_id,
            "parent_id": parent_id,
            "family_id": family_id,
            "parent_content": entry.get("parent_content"),
            "header_path": entry.get("header_path"),
            "parent_path": parent_path,
            "chunk_index": int(entry.get("child_index", 0)),
            "content_preview": (entry.get("content") or "")[:240],
            "final_score": final_score,
            "display_score": display_score,
            "vector_score": vector_score,
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
    family_ids: list[str] = []
    for hit in fused:
        if isinstance(hit, HierarchicalHit):
            if hit.parent_id:
                parent_ids.append(hit.parent_id)
            if hit.child_id:
                child_ids.append(hit.child_id)
            grandchild_ids.append(hit.grandchild_id)
            if hit.family_id:
                family_ids.append(hit.family_id)
            continue
        entry = pool.get(hit.chunk_id) or {}
        parent_id = entry.get("parent_id")
        if parent_id:
            parent_ids.append(str(parent_id))
        child_ids.append(hit.chunk_id)
        grandchild_ids.extend(entry.get("grandchild_ids") or [])
        if entry.get("family_id"):
            family_ids.append(str(entry["family_id"]))
    return {
        "family_ids": list(dict.fromkeys(family_ids)),
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
    """Cascade W1–W4 recall + hierarchical vector aggregation (v1.62)."""
    del recall_k  # replaced by TIER_RECALL_K
    client = get_neo4j_client()
    workflow_log: list[dict[str, Any]] = []
    vram_peak_mb = 0
    scope_meta = scope_meta or {}
    k_family = TIER_RECALL_K["family"]
    k_parent = TIER_RECALL_K["parent"]
    k_child = TIER_RECALL_K["child"]
    k_gc = TIER_RECALL_K["grandchild"]

    def _log_phase(entry: dict[str, Any]) -> None:
        workflow_log.append(entry)
        logger.info("search_phase", **entry)

    def _rescore_pool(
        label: str, ids: list[str], q_vec: np.ndarray
    ) -> dict[str, float]:
        meta = client.get_node_vectors(label, ids)
        out: dict[str, float] = {}
        for nid, row in meta.items():
            vec = row.get("vector")
            if vec is None:
                out[nid] = 0.0
                continue
            out[nid] = cosine_sim(q_vec, np.asarray(vec, dtype=np.float32))
        return out

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
                "rerank_over_limit": False,
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
    q_coarse = matryoshka_truncate(q_full, coarse_dim).tolist()

    # --- W1 Family ---
    _publish_phase_progress(job_id, workflow_log, "family_recall", span_id=span_id)
    t0 = time.perf_counter()
    fam_vec_hits = client.vector_search_coarse_family(
        coarse_dim, q_coarse, k_family, allowed_paths=allowed_paths
    )
    fam_bm25_hits = client.bm25_search_family(query, k_family, allowed_paths=allowed_paths)
    fam_pool: dict[str, dict[str, Any]] = {}
    fam_v: dict[str, float] = {}
    fam_b: dict[str, float] = {}
    for row in fam_vec_hits:
        node = node_to_dict(row["family"])
        fam_pool[node["id"]] = node
        fam_v[node["id"]] = float(row.get("vector_score") or 0.0)
    for row in fam_bm25_hits:
        node = node_to_dict(row["family"])
        fam_pool[node["id"]] = node
        fam_b[node["id"]] = float(row.get("bm25_score") or 0.0)
    fam_v.update(_rescore_pool("Knowledgechunk_family", list(fam_pool.keys()), q_full))
    fam_fused = fuse_tier_pool(
        list(fam_pool.keys()), fam_v, fam_b, w1=w1, w2=w2, use_minmax_fallback=use_minmax_fallback, top_k=k_family
    )
    family_ids = [h.chunk_id for h in fam_fused]
    family_vector_by_id = {h.chunk_id: h.vector_score for h in fam_fused}
    _log_phase(
        {
            "phase": "family_recall",
            "status": "done",
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "hit_count": len(family_ids),
            "pool_size": len(fam_pool),
        }
    )

    # --- W2 Parent ---
    _publish_phase_progress(job_id, workflow_log, "parent_recall", span_id=span_id)
    t0 = time.perf_counter()
    par_vec_hits = client.vector_search_coarse_parents(
        coarse_dim, q_coarse, k_parent, allowed_paths=allowed_paths, allowed_family_ids=family_ids or None
    )
    par_bm25_hits = client.bm25_search_parents(
        query, k_parent, allowed_paths=allowed_paths, allowed_family_ids=family_ids or None
    )
    par_pool: dict[str, dict[str, Any]] = {}
    par_v: dict[str, float] = {}
    par_b: dict[str, float] = {}
    parent_family: dict[str, str] = {}
    for row in par_vec_hits + par_bm25_hits:
        node = node_to_dict(row["parent"])
        fam = node_to_dict(row.get("family"))
        par_pool[node["id"]] = node
        parent_family[node["id"]] = fam.get("id") or node.get("family_id") or ""
        if "vector_score" in row:
            par_v[node["id"]] = float(row["vector_score"] or 0.0)
        if "bm25_score" in row:
            par_b[node["id"]] = float(row["bm25_score"] or 0.0)
    par_v.update(_rescore_pool("Knowledgechunk", list(par_pool.keys()), q_full))
    par_fused = fuse_tier_pool(
        list(par_pool.keys()), par_v, par_b, w1=w1, w2=w2, use_minmax_fallback=use_minmax_fallback, top_k=k_parent
    )
    parent_ids = [h.chunk_id for h in par_fused]
    parent_vector_by_id = {h.chunk_id: h.vector_score for h in par_fused}
    _log_phase(
        {
            "phase": "parent_recall",
            "status": "done",
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "hit_count": len(parent_ids),
            "pool_size": len(par_pool),
        }
    )

    # --- W3 Child ---
    _publish_phase_progress(job_id, workflow_log, "child_recall", span_id=span_id)
    t0 = time.perf_counter()
    ch_vec_hits = client.vector_search_coarse_children_v162(
        coarse_dim, q_coarse, k_child, allowed_paths=allowed_paths, allowed_parent_ids=parent_ids or None
    )
    ch_bm25_hits = client.bm25_search_children_v162(
        query, k_child, allowed_paths=allowed_paths, allowed_parent_ids=parent_ids or None
    )
    ch_pool: dict[str, dict[str, Any]] = {}
    ch_v: dict[str, float] = {}
    ch_b: dict[str, float] = {}
    child_parent: dict[str, str] = {}
    child_family: dict[str, str] = {}
    for row in ch_vec_hits + ch_bm25_hits:
        node = node_to_dict(row["child"])
        parent = node_to_dict(row.get("parent"))
        fam = node_to_dict(row.get("family"))
        ch_pool[node["id"]] = node
        child_parent[node["id"]] = parent.get("id") or node.get("parent_id") or ""
        child_family[node["id"]] = fam.get("id") or ""
        if "vector_score" in row:
            ch_v[node["id"]] = float(row["vector_score"] or 0.0)
        if "bm25_score" in row:
            ch_b[node["id"]] = float(row["bm25_score"] or 0.0)
    ch_v.update(_rescore_pool("Knowledgechunk_sen", list(ch_pool.keys()), q_full))
    ch_fused = fuse_tier_pool(
        list(ch_pool.keys()), ch_v, ch_b, w1=w1, w2=w2, use_minmax_fallback=use_minmax_fallback, top_k=k_child
    )
    child_ids = [h.chunk_id for h in ch_fused]
    child_vector_by_id = {h.chunk_id: h.vector_score for h in ch_fused}
    _log_phase(
        {
            "phase": "child_recall",
            "status": "done",
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "hit_count": len(child_ids),
            "pool_size": len(ch_pool),
        }
    )

    # --- W4 Grandchild ---
    _publish_phase_progress(job_id, workflow_log, "grandchild_recall", span_id=span_id)
    t0 = time.perf_counter()
    gc_vec_hits = client.vector_search_coarse_grandchildren(
        coarse_dim, q_coarse, k_gc, allowed_paths=allowed_paths, allowed_child_ids=child_ids or None
    )
    gc_bm25_hits = client.bm25_search_grandchildren(
        query, k_gc, allowed_paths=allowed_paths, allowed_child_ids=child_ids or None
    )
    gc_pool: dict[str, dict[str, Any]] = {}
    gc_v: dict[str, float] = {}
    gc_b: dict[str, float] = {}
    for row in gc_vec_hits + gc_bm25_hits:
        node = node_to_dict(row["grandchild"])
        child = node_to_dict(row.get("child"))
        parent = node_to_dict(row.get("parent"))
        fam = node_to_dict(row.get("family"))
        gc_pool[node["id"]] = {
            **node,
            "child_id": child.get("id") or node.get("child_id"),
            "parent_id": parent.get("id") or node.get("parent_id"),
            "family_id": fam.get("id") or "",
            "parent_content": parent.get("content") or "",
            "header_path": parent.get("header_path") or "",
            "source_file": node.get("source_file") or fam.get("source_file") or "",
            "child_index": int(child.get("child_index") or 0),
        }
        if "vector_score" in row:
            gc_v[node["id"]] = float(row["vector_score"] or 0.0)
        if "bm25_score" in row:
            gc_b[node["id"]] = float(row["bm25_score"] or 0.0)
    gc_v.update(_rescore_pool("Knowledgechunk_grand", list(gc_pool.keys()), q_full))
    gc_fused = fuse_tier_pool(
        list(gc_pool.keys()), gc_v, gc_b, w1=w1, w2=w2, use_minmax_fallback=use_minmax_fallback, top_k=k_gc
    )
    _log_phase(
        {
            "phase": "grandchild_recall",
            "status": "done",
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "hit_count": len(gc_fused),
            "pool_size": len(gc_pool),
        }
    )

    # --- Hierarchical aggregation ---
    _publish_phase_progress(job_id, workflow_log, "hierarchical_fusion", span_id=span_id)
    t0 = time.perf_counter()
    paths: list[dict[str, Any]] = []
    for h in gc_fused:
        entry = gc_pool[h.chunk_id]
        cid = entry.get("child_id") or ""
        pid = entry.get("parent_id") or ""
        fid = entry.get("family_id") or child_family.get(cid) or parent_family.get(pid) or ""
        paths.append(
            {
                "grandchild_id": h.chunk_id,
                "child_id": cid,
                "parent_id": pid,
                "family_id": fid,
                "family_vector": family_vector_by_id.get(fid, 0.0),
                "parent_vector": parent_vector_by_id.get(pid, 0.0),
                "child_vector": child_vector_by_id.get(cid, 0.0),
                "grandchild_vector": h.vector_score,
                "bm25_score": h.bm25_score,
                "content": entry.get("content") or "",
                "parent_content": entry.get("parent_content") or "",
                "header_path": entry.get("header_path") or "",
                "source_file": entry.get("source_file") or "",
                "child_index": entry.get("child_index") or 0,
            }
        )
    fused = aggregate_hierarchical_scores(paths)[: max(rerank_k, TIER_RECALL_K["rerank"])]
    _log_phase(
        {
            "phase": "hierarchical_fusion",
            "status": "done",
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "w1": w1,
            "w2": w2,
            "pool_size": len(paths),
            "rerank_k": rerank_k,
        }
    )

    pool = {h.grandchild_id: {
        "id": h.grandchild_id,
        "parent_id": h.parent_id,
        "child_id": h.child_id,
        "family_id": h.family_id,
        "child_index": h.child_index,
        "content": h.content,
        "parent_content": h.parent_content,
        "header_path": h.header_path,
        "source_file": h.source_file,
    } for h in fused}

    rerank_inputs = [h.content for h in fused if h.content.strip()]
    parent_paths = {h.grandchild_id: h.source_file for h in fused if h.source_file}

    # Token estimate for W5 gate
    rerank_token_count = 0
    rerank_over_limit = False
    if rerank_inputs:
        try:
            rerank_token_count = jina_runtime.estimate_rerank_prompt_tokens(query, rerank_inputs)
            rerank_over_limit = rerank_token_count > GRANDCHILD_RERANK_TOKEN_LIMIT
        except Exception as exc:
            logger.warning("rerank_token_estimate_failed", error=str(exc))

    _publish_phase_progress(job_id, workflow_log, None, span_id=span_id)
    return {
        "empty_scope": False,
        "workflow_log": workflow_log,
        "pool": pool,
        "fused": fused,
        "rerank_inputs": rerank_inputs,
        "vector_hits": gc_vec_hits,
        "bm25_hits": gc_bm25_hits,
        "parent_paths": parent_paths,
        "vram_peak_mb": vram_peak_mb,
        "rerank_token_count": rerank_token_count,
        "rerank_over_limit": rerank_over_limit,
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

        rerank_token_count = int(fusion_data.get("rerank_token_count") or 0)
        if not rerank_token_count and rerank_inputs:
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
        fusion_meta["rerank_over_limit"] = bool(fusion_data.get("rerank_over_limit"))

        def _fused_id(h: Any) -> str:
            return h.grandchild_id if isinstance(h, HierarchicalHit) else h.chunk_id

        if job_id:
            slim_pool = _slim_pool_for_pending(pool)
            pending_payload = {
                "query": query,
                "rerank_inputs": rerank_inputs,
                "fused_chunk_ids": [_fused_id(h) for h in fused],
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
                        "chunk_id": _fused_id(h),
                        "final_score": h.final_score,
                        "display_score": h.display_score,
                        "vector_score": float(getattr(h, "vector_score", 0.0) or 0.0),
                    }
                    for h in fused
                ],
                "parent_paths": parent_paths,
                "retrieval_tree": retrieval_tree,
                "w1": w1,
                "w2": w2,
                "recall_k": recall_k,
                "coarse_dim": coarse_dim,
                "allowed_paths": allowed_paths,
                "rerank_over_limit": bool(fusion_data.get("rerank_over_limit")),
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
            vector_score=float(item.get("vector_score", 0.0) or 0.0),
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


@check_health
@worker_trace("extract_memory_graph")
def extract_memory_graph(
    query_text: str,
    grandchild_ids: list[str],
    user_query_id: str | None = None,
    session_id: str | None = None,
    traceparent: str = "",
    span_id: str | None = None,
) -> dict[str, Any]:
    """Manual GraphRAG extract: Liquid → Neo4j graph + communities + episodic Redis."""
    from app.services import episodic_memory, graph_community, liquid_extract, liquid_runtime
    from app.services.memory_key import (
        compute_memory_key,
        new_memory_id,
        source_query_id as resolve_source_query_id,
    )

    del traceparent
    client = get_neo4j_client()
    uq_id = resolve_source_query_id(query_text, user_query_id)
    mem_key = compute_memory_key(uq_id, grandchild_ids)
    memory_id = new_memory_id()

    chunk_rows = client.get_grandchild_contents(grandchild_ids)
    if not chunk_rows:
        raise ValueError("No Knowledgechunk_grand nodes found for grandchild_ids")

    chunks = [
        {
            "id": row["id"],
            "grandchild_id": row["id"],
            "content": row.get("content") or "",
            "source_file": row.get("source_file"),
        }
        for row in chunk_rows
    ]

    llm = None
    try:
        llm = liquid_runtime.load_extract_model()
        graph = liquid_extract.extract_graph_from_chunks(chunks, query_text, llm=llm)
        communities = graph_community.partition_entities(graph.entities, graph.relations)
        summaries = graph_community.build_community_summaries(communities, graph, llm=llm)

        entity_payload = [
            {
                "entity_id": e.entity_id,
                "name": e.name,
                "type": e.type,
                "grandchild_id": grandchild_ids[0] if grandchild_ids else None,
            }
            for e in graph.entities
        ]
        relation_payload = [
            {
                "source_id": r.source_id,
                "target_id": r.target_id,
                "type": r.type,
                "weight": r.weight,
            }
            for r in graph.relations
        ]
        claim_payload = [
            {
                "claim_id": c.claim_id,
                "text": c.text,
                "entity_id": c.entity_id,
                "confidence": c.confidence,
                "grandchild_id": c.grandchild_id or (grandchild_ids[0] if grandchild_ids else None),
            }
            for c in graph.claims
        ]
        community_payload = [
            {
                "community_id": c.community_id,
                "level": c.level,
                "entity_ids": c.entity_ids,
            }
            for c in communities
        ]
        summary_payload = [
            {
                "summary_id": s.summary_id,
                "community_id": s.community_id,
                "level": s.level,
                "text": s.text,
            }
            for s in summaries
        ]

        result = client.merge_memory_graph(
            memory_key=mem_key,
            memory_id=memory_id,
            query_text=query_text,
            user_query_id=uq_id,
            trace_id=span_id,
            summary=graph.summary,
            grandchild_ids=grandchild_ids,
            entities=entity_payload,
            relations=relation_payload,
            claims=claim_payload,
            communities=community_payload,
            summaries=summary_payload,
        )

        if session_id:
            retrieval_tree = retrieval_memory.load_retrieval_tree(session_id)
            tree_payload = (retrieval_tree or {}).get("retrieval_tree") or {}
            episodic_memory.save_episodic_session(
                session_id,
                query=query_text,
                grandchild_ids=grandchild_ids,
                memory_key=mem_key,
                span_id=span_id,
                retrieval_tree=tree_payload,
            )

        push_metrics(
            {
                "stage": "extract_memory_graph",
                "entities": result.get("entities_created", 0),
                "communities": result.get("communities_created", 0),
            }
        )
        return result
    finally:
        if llm is not None:
            liquid_runtime.release_extract_model(llm)
