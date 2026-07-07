"""
db/neo4j_client.py — Thin, typed wrapper around the official neo4j Python driver.

Responsibilities (Backend §2 — STRICT module boundaries):
  • Driver singleton + session context manager.
  • Retry on transient errors (max 2 attempts per error-handling spec §3).
  • Typed CRUD methods for every node label + relationship in neo4j-schema-v1.1.md.
  • Vector search helpers (HNSW cosine on :Knowledge + :KnowledgeChunk).
  • Fulltext BM25 search helpers (Neo4j fulltext + db.index.fulltext.queryNodes).
  • All Cypher uses parameterized queries (no string interpolation) — defense
    against Cypher injection.

This module NEVER embeds, NEVER chunks, NEVER scores — it ONLY persists + queries.
The PipelineOrchestrator owns coordination; the EmbeddingModule produces vectors;
the RetrievalModule scores results.
"""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from neo4j import Driver, GraphDatabase, ManagedTransaction, Session

from app.core.config import settings
from app.core.constants import NEO4J_MAX_RETRIES
from app.core.exceptions import Neo4jError
from app.core.logging import get_logger, log_pipeline_event
from app.models.neo4j_models import (
    Knowledge,
    KnowledgeChunk,
    Memory,
    MemoryCart,
    UserQuery,
    UserQueryChunk,
)

logger = get_logger("rag.db.neo4j")


# ─── Transient error detection ────────────────────────────────────────────────

_TRANSIENT_CODE_PREFIXES = (
    "Neo.TransientError",
    "Neo.ClientError.Transaction",
    "Neo.TransientError.General.DatabaseUnavailable",
    "ServiceUnavailable",
    "Neo.ClientError.Database.DatabaseUnavailable",
)


def _is_transient(exc: Exception) -> bool:
    msg = str(exc)
    if any(p in msg for p in _TRANSIENT_CODE_PREFIXES):
        return True
    # Connectivity / network
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return True
    return False


# ─── Client ───────────────────────────────────────────────────────────────────


class Neo4jClient:
    """Driver singleton + typed CRUD methods.

    Instantiate once at app startup (lifespan) and share across requests.
    Sessions are lightweight + thread-safe; the driver itself is the heavy
    resource (connection pool).
    """

    def __init__(
        self,
        uri: str,
        user: str,
        password: str,
        database: str = "neo4j",
        max_retries: int = NEO4J_MAX_RETRIES,
    ) -> None:
        self._uri = uri
        self._user = user
        self._database = database
        self._max_retries = max_retries
        try:
            self._driver: Driver = GraphDatabase.driver(
                uri, auth=(user, password), max_connection_pool_size=50
            )
        except Exception as exc:
            raise Neo4jError(
                f"Failed to initialize Neo4j driver: {exc}",
                details={"uri": uri, "user": user},
                stage="neo4j_init",
            ) from exc

    # ─── lifecycle ──────────────────────────────────────────────────────────

    def verify_connectivity(self) -> None:
        """Raise Neo4jError if the database is unreachable."""
        try:
            self._driver.verify_connectivity()
        except Exception as exc:
            raise Neo4jError(
                f"Neo4j unreachable: {exc}",
                details={"uri": self._uri},
                stage="neo4j_connectivity",
            ) from exc

    def close(self) -> None:
        try:
            self._driver.close()
        except Exception:
            pass

    @property
    def driver(self) -> Driver:
        return self._driver

    @contextmanager
    def session(self, *, write: bool = False) -> Iterable[Session]:
        """Yield a session bound to the configured database."""
        sess = self._driver.session(database=self._database)
        try:
            yield sess
        finally:
            sess.close()

    # ─── low-level write w/ retry ───────────────────────────────────────────

    def _run_write_with_retry(self, cypher: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Run a write transaction with transient-error retry (max 2)."""
        last_exc: Optional[Exception] = None
        for attempt in range(self._max_retries + 1):
            try:
                with self.session(write=True) as sess:

                    def _tx(txn: ManagedTransaction):
                        result = txn.run(cypher, params)
                        return [r.data() for r in result]

                    return sess.execute_write(_tx)
            except Exception as exc:
                last_exc = exc
                if _is_transient(exc) and attempt < self._max_retries:
                    backoff = 0.25 * (2 ** attempt)
                    logger.warning(
                        "neo4j.transient_retry",
                        extra={
                            "event": "neo4j.transient_retry",
                            "attempt": attempt + 1,
                            "backoff_ms": backoff * 1000,
                            "error": str(exc),
                        },
                    )
                    time.sleep(backoff)
                    continue
                break
        # Non-transient or out of retries
        raise Neo4jError(
            f"Neo4j write failed after {self._max_retries + 1} attempt(s): {last_exc}",
            details={"cypher": cypher[:200], "params_keys": list(params.keys())},
            stage="neo4j_write",
            retry_count=self._max_retries,
        ) from last_exc

    def _run_read_with_retry(self, cypher: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        last_exc: Optional[Exception] = None
        for attempt in range(self._max_retries + 1):
            try:
                with self.session(write=False) as sess:
                    result = sess.run(cypher, params)
                    return [r.data() for r in result]
            except Exception as exc:
                last_exc = exc
                if _is_transient(exc) and attempt < self._max_retries:
                    time.sleep(0.25 * (2 ** attempt))
                    continue
                break
        raise Neo4jError(
            f"Neo4j read failed after {self._max_retries + 1} attempt(s): {last_exc}",
            details={"cypher": cypher[:200]},
            stage="neo4j_read",
            retry_count=self._max_retries,
        ) from last_exc

    def list_chunks_for_source_file(self, source_file: str) -> List[Dict[str, Any]]:
        """Return :Knowledge (parents) + :KnowledgeChunk for a document by source_file.
        (source_file based; experiment node removed)
        """
        cypher = """
        MATCH (k:Knowledge {source_file: $source_file})
        OPTIONAL MATCH (k)-[:HAS_CHUNK]->(c:KnowledgeChunk)
        RETURN
          collect(DISTINCT k) AS parents,
          collect(c) AS children
        """
        rows = self._run_read_with_retry(cypher, {"source_file": source_file})
        if not rows:
            return []
        parents = [p for p in (rows[0].get("parents") or []) if p]
        children = [ch for ch in (rows[0].get("children") or []) if ch]

        result: List[Dict[str, Any]] = []
        for p in sorted(parents, key=lambda x: x.get("chunk_index") or 0):
            pp = dict(p)
            pp["node_type"] = "knowledge"
            result.append(pp)
        for ch in sorted(children, key=lambda x: x.get("chunk_index") or 0):
            cch = dict(ch)
            cch["node_type"] = "knowledge_chunk"
            result.append(cch)
        return result

    def get_original_knowledge(self, source_file: str) -> Optional[Dict[str, Any]]:
        """Return the raw uploaded :Knowledge placeholder (embedding_method='Upload').

        Original file content at upload time (pre any ingest). Used by Documents view.
        """
        cypher = """
        MATCH (k:Knowledge {source_file: $source_file, embedding_method: 'Upload'})
        WHERE k.text IS NOT NULL
        RETURN k
        ORDER BY coalesce(k.created_at, datetime('1900-01-01')) DESC
        LIMIT 1
        """
        rows = self._run_read_with_retry(cypher, {"source_file": source_file})
        return dict(rows[0]["k"]) if rows and rows[0].get("k") else None

    def get_knowledge_by_source(self, source_file: str, prefer_non_upload: bool = False) -> Optional[Dict[str, Any]]:
        """Return one Knowledge row for a source_file.

        If prefer_non_upload, prefer LongText/ingested parents over Upload placeholder.
        """
        if prefer_non_upload:
            cypher = """
            MATCH (k:Knowledge {source_file: $sf})
            WITH k ORDER BY
              CASE WHEN k.embedding_method = 'Upload' THEN 1 ELSE 0 END,
              coalesce(k.created_at, datetime('1900-01-01')) DESC
            LIMIT 1
            RETURN k
            """
        else:
            cypher = """
            MATCH (k:Knowledge {source_file: $sf})
            RETURN k ORDER BY coalesce(k.created_at, datetime('1900-01-01')) DESC LIMIT 1
            """
        rows = self._run_read_with_retry(cypher, {"sf": source_file})
        return dict(rows[0]["k"]) if rows and rows[0].get("k") else None

    # recent_* methods removed (no :Experiment node)

    # ─── Knowledge + KnowledgeChunk (ingest) ────────────────────────────────

    def create_knowledge(self, k: Knowledge) -> Dict[str, Any]:
        cypher = """
        CREATE (n:Knowledge {
          id: $id,
          source_file: $source_file,
          total_tokens: $total_tokens,
          embedding_method: $embedding_method,
          created_at: datetime($created_at),
          vector: $vector,
          text: $text,
          chunk_index: $chunk_index,
          char_start: $char_start,
          char_end: $char_end
        })
        RETURN n
        """
        params = {
            "id": k.id,
            "source_file": k.source_file,
            "total_tokens": k.total_tokens,
            "embedding_method": k.embedding_method,
            "created_at": k.created_at.isoformat(),
            "vector": list(k.vector) if k.vector is not None else None,
            "text": k.text,
            "chunk_index": k.chunk_index,
            "char_start": k.char_start,
            "char_end": k.char_end,
        }
        rows = self._run_write_with_retry(cypher, params)
        return rows[0]["n"] if rows else {}

    def create_chunk(self, c: KnowledgeChunk, parent_knowledge_id: str) -> Dict[str, Any]:
        """Create a KnowledgeChunk + HAS_CHUNK edge to its parent Knowledge."""
        cypher = """
        MATCH (k:Knowledge {id: $parent_id})
        CREATE (c:KnowledgeChunk {
          id: $id,
          parent_doc_id: $parent_doc_id,
          chunk_index: $chunk_index,
          text: $text,
          token_count: $token_count,
          chunk_method: $chunk_method,
          chunking_time_ms: $chunking_time_ms,
          embedding_time_ms: $embedding_time_ms,
          embedding_method: $embedding_method,
          vector: $vector,
          char_start: $char_start,
          char_end: $char_end,
          section: $section
        })
        MERGE (k)-[:HAS_CHUNK]->(c)
        RETURN c
        """
        params = {
            "parent_id": parent_knowledge_id,
            "id": c.id,
            "parent_doc_id": c.parent_doc_id,
            "chunk_index": c.chunk_index,
            "text": c.text,
            "token_count": c.token_count,
            "chunk_method": c.chunk_method,
            "chunking_time_ms": c.chunking_time_ms,
            "embedding_time_ms": c.embedding_time_ms,
            "embedding_method": c.embedding_method,
            "vector": list(c.vector),
            "char_start": c.char_start,
            "char_end": c.char_end,
            "section": c.section,
        }
        rows = self._run_write_with_retry(cypher, params)
        return rows[0]["c"] if rows else {}

    def list_documents(self, page: int = 1, page_size: int = 20) -> Tuple[List[Dict[str, Any]], int]:
        """Logical documents (one per unique source_file).

        Returns the first-seen Knowledge node per source_file (preferring
        upload-time placeholders so size/createdAt reflect the upload, not a
        later ingest run).
        """
        skip = (page - 1) * page_size
        cypher = """
        MATCH (k:Knowledge)
        WITH k.source_file AS source_file,
             head(collect(k)) AS first,
             count(k) AS chunk_count,
             // collect distinct embedding_methods for badges
             collect(DISTINCT k.embedding_method) AS methods
        // representative = head of collect (Upload placeholders created first are preferred for display)
        RETURN collect({
          id: source_file,
          filename: source_file,
          contentType: 'text/markdown',
          sizeBytes: size(first.text),
          totalChunks: chunk_count,
          createdAt: first.created_at,
          representativeEmbeddingMethod: first.embedding_method,
          kinds: methods
        }) AS items, count(DISTINCT source_file) AS total
        """
        rows = self._run_read_with_retry(cypher, {})
        if not rows:
            log_pipeline_event(logger, "documents.list", "observed 0 documents (no Knowledge nodes?)", total=0)
            return [], 0
        items = rows[0].get("items", []) or []
        total = rows[0].get("total", 0) or 0
        # Sort by createdAt desc (Neo4j collect() preserves encounter order — re-sort client-side)
        items_sorted = sorted(items, key=lambda x: x.get("createdAt", ""), reverse=True)
        page_items = items_sorted[skip : skip + page_size]
        # observation for "ingest documents" flow: show which neo4j Knowledge source_file records contribute to the list + document count
        log_pipeline_event(
            logger,
            "documents.list",
            "observed neo4j Knowledge records for documents list",
            total=total,
            page_returned=len(page_items),
            sample_filenames=[str(it.get("filename")) for it in page_items[:3]] if page_items else [],
            # note: if sample empty but total>0, inspect the list_documents Cypher scoping
        )
        return page_items, total

    def get_document_text(self, source_file: str) -> Optional[str]:
        """Return the stored text for an uploaded document (pre-ingest).

        Reads ONLY from upload-time placeholder nodes
        (embedding_method='Upload') so re-ingesting a document doesn't double-
        count windowed text from prior ingest runs.
        """
        cypher = """
        MATCH (k:Knowledge {source_file: $source_file, embedding_method: 'Upload'})
        WHERE k.text IS NOT NULL
        RETURN k.text AS text, k.chunk_index AS idx
        ORDER BY coalesce(idx, 0)
        """
        rows = self._run_read_with_retry(cypher, {"source_file": source_file})
        if not rows:
            return None
        return "\n\n".join(r["text"] for r in rows if r.get("text"))

    def delete_document(self, source_file: str) -> int:
        """Delete upload-time placeholder Knowledge nodes for a source file.

        Only removes :Knowledge with embedding_method='Upload' (pre-ingest placeholders).
        Preserves any ingest-time Knowledge + child KnowledgeChunks.
        Returns the count of deleted Knowledge nodes.
        """
        cypher = """
        MATCH (k:Knowledge {source_file: $source_file, embedding_method: 'Upload'})
        OPTIONAL MATCH (k)-[:HAS_CHUNK]->(c:KnowledgeChunk)
        DETACH DELETE c, k
        RETURN count(k) AS deleted
        """
        rows = self._run_write_with_retry(cypher, {"source_file": source_file})
        return rows[0].get("deleted", 0) if rows else 0

    # ─── UserQuery + UserQueryChunk ─────────────────────────────────────────

    def create_user_query(self, q: UserQuery) -> Dict[str, Any]:
        cypher = """
        CREATE (n:UserQuery {
          id: $id,
          text: $text,
          total_tokens: $total_tokens,
          embedding_method: $embedding_method,
          created_at: datetime($created_at),
          vector: $vector
        })
        RETURN n
        """
        params = {
            "id": q.id,
            "text": q.text,
            "total_tokens": q.total_tokens,
            "embedding_method": q.embedding_method,
            "created_at": q.created_at.isoformat(),
            "vector": list(q.vector),
        }
        rows = self._run_write_with_retry(cypher, params)
        return rows[0]["n"] if rows else {}

    def create_user_query_chunk(self, qc: UserQueryChunk) -> Dict[str, Any]:
        cypher = """
        MATCH (q:UserQuery {id: $parent_id})
        CREATE (c:UserQueryChunk {
          id: $id,
          parent_query_id: $parent_query_id,
          chunk_index: $chunk_index,
          text: $text,
          token_count: $token_count,
          chunk_method: $chunk_method,
          embedding_time_ms: $embedding_time_ms,
          vector: $vector
        })
        MERGE (q)-[:HAS_CHUNK]->(c)
        RETURN c
        """
        params = {
            "parent_id": qc.parent_query_id,
            "id": qc.id,
            "parent_query_id": qc.parent_query_id,
            "chunk_index": qc.chunk_index,
            "text": qc.text,
            "token_count": qc.token_count,
            "chunk_method": qc.chunk_method,
            "embedding_time_ms": qc.embedding_time_ms,
            "vector": list(qc.vector),
        }
        rows = self._run_write_with_retry(cypher, params)
        return rows[0]["c"] if rows else {}

    # ─── Vector search (HNSW cosine) ────────────────────────────────────────

    def vector_search_chunks(
        self,
        query_vector: List[float],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """Vector search on :KnowledgeChunk (the child retrieval targets).

        Returns rows with chunk + parent metadata for orchestrator scoring.
        """
        cypher = """
        CALL db.index.vector.queryNodes('knowledgechunk_vector', $top_k, $vector)
        YIELD node, score
        WHERE node:KnowledgeChunk
        MATCH (parent:Knowledge)-[:HAS_CHUNK]->(node)
        RETURN node AS chunk,
               parent AS parent,
               score AS vector_score
        ORDER BY score DESC
        LIMIT $top_k
        """
        params = {"top_k": top_k, "vector": list(query_vector)}
        return self._run_read_with_retry(cypher, params)

    def vector_search_parents(
        self,
        query_vector: List[float],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """Vector search on :Knowledge parent nodes (used by LongText path)."""
        cypher = """
        CALL db.index.vector.queryNodes('knowledge_vector', $top_k, $vector)
        YIELD node, score
        WHERE node:Knowledge
        RETURN node AS parent,
               score AS vector_score
        ORDER BY score DESC
        LIMIT $top_k
        """
        params = {"top_k": top_k, "vector": list(query_vector)}
        return self._run_read_with_retry(cypher, params)

    # ─── BM25 fulltext search ───────────────────────────────────────────────

    def bm25_search_chunks(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        """BM25 search on :KnowledgeChunk via the `knowledgechunk_text` fulltext index.

        Returns rows with chunk + parent + bm25 score.
        """
        # Escape Lucene special chars in the raw query.
        safe = _escape_lucene_query(query)
        if not safe.strip():
            return []
        cypher = """
        CALL db.index.fulltext.queryNodes('knowledgechunk_text', $query)
        YIELD node, score
        WHERE node:KnowledgeChunk
        MATCH (parent:Knowledge)-[:HAS_CHUNK]->(node)
        RETURN node AS chunk,
               parent AS parent,
               score AS bm25_score
        ORDER BY score DESC
        LIMIT $top_k
        """
        params = {"query": safe, "top_k": top_k}
        return self._run_read_with_retry(cypher, params)

    def bm25_search_parents(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        """BM25 search on :Knowledge parent nodes via `knowledge_text` index."""
        safe = _escape_lucene_query(query)
        if not safe.strip():
            return []
        cypher = """
        CALL db.index.fulltext.queryNodes('knowledge_text', $query)
        YIELD node, score
        WHERE node:Knowledge
        RETURN node AS parent,
               score AS bm25_score
        ORDER BY score DESC
        LIMIT $top_k
        """
        params = {"query": safe, "top_k": top_k}
        return self._run_read_with_retry(cypher, params)

    # ─── Memory + MemoryCart ────────────────────────────────────────────────

    def create_memory(self, m: Memory) -> Dict[str, Any]:
        """Create a :Memory node + (:UserQuery)-[:TRIGGERED]->(:Memory)
        + (:Memory)-[:RETRIEVED]->(:KnowledgeChunk) edges."""
        cypher = """
        MATCH (q:UserQuery {id: $user_query_id})
        CREATE (m:Memory {
          id: $id,
          user_query_id: $user_query_id,
          timestamp: datetime($timestamp),
          success_score: $success_score,
          notes: $notes,
          query_text: $query_text,
          chunk_id: $chunk_id,
          chunk_text: $chunk_text,
          score: $score,
          vector_score: $vector_score,
          bm25_score: $bm25_score,
          fused_score: $fused_score,
          reranker_score: $reranker_score
        })
        MERGE (q)-[:TRIGGERED]->(m)
        WITH m
        WHERE $chunk_id IS NOT NULL
        MATCH (c:KnowledgeChunk {id: $chunk_id})
        MERGE (m)-[:RETRIEVED]->(c)
        RETURN m
        """
        params = {
            "id": m.id,
            "user_query_id": m.user_query_id,
            "timestamp": m.timestamp.isoformat(),
            "success_score": m.success_score,
            "notes": m.notes,
            "query_text": m.query_text,
            "chunk_id": m.chunk_id,
            "chunk_text": m.chunk_text,
            "score": m.score,
            "vector_score": m.vector_score,
            "bm25_score": m.bm25_score,
            "fused_score": m.fused_score,
            "reranker_score": m.reranker_score,
        }
        rows = self._run_write_with_retry(cypher, params)
        return rows[0]["m"] if rows else {}

    def list_memories(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        skip = (page - 1) * page_size
        cypher = """
        MATCH (m:Memory)
        OPTIONAL MATCH (cart:MemoryCart)-[:CONTAINS]->(m)
        WITH m, cart
        ORDER BY m.timestamp DESC
        RETURN collect({
          memory: m,
          selected: cart IS NOT NULL
        }) AS items, count(m) AS total
        """
        rows = self._run_read_with_retry(cypher, {})
        if not rows:
            return [], 0
        items = rows[0].get("items", []) or []
        total = rows[0].get("total", 0) or 0
        return items[skip : skip + page_size], total

    def create_memory_cart(self, cart: MemoryCart) -> Dict[str, Any]:
        cypher = """
        CREATE (c:MemoryCart {
          id: $id,
          name: $name,
          description: $description,
          created_at: datetime($created_at),
          updated_at: datetime($updated_at),
          researcher_id: $researcher_id
        })
        RETURN c
        """
        params = {
            "id": cart.id,
            "name": cart.name,
            "description": cart.description,
            "created_at": cart.created_at.isoformat(),
            "updated_at": cart.updated_at.isoformat(),
            "researcher_id": cart.researcher_id,
        }
        rows = self._run_write_with_retry(cypher, params)
        return rows[0]["c"] if rows else {}

    def list_memory_carts(self) -> List[Dict[str, Any]]:
        cypher = """
        MATCH (c:MemoryCart)
        OPTIONAL MATCH (c)-[:CONTAINS]->(m:Memory)
        RETURN c AS cart, count(m) AS memory_count
        ORDER BY c.updated_at DESC
        """
        return self._run_read_with_retry(cypher, {})

    def get_memory_cart(self, cart_id: str) -> Optional[Dict[str, Any]]:
        cypher = """
        MATCH (c:MemoryCart {id: $id})
        OPTIONAL MATCH (c)-[:CONTAINS]->(m:Memory)
        RETURN c AS cart, collect(m) AS memories
        """
        rows = self._run_read_with_retry(cypher, {"id": cart_id})
        if not rows:
            return None
        return rows[0]

    def update_memory_cart(
        self,
        cart_id: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        cypher = """
        MATCH (c:MemoryCart {id: $id})
        SET c.name = coalesce($name, c.name),
            c.description = $description,
            c.updated_at = datetime()
        RETURN c
        """
        # description can be intentionally set to null
        params = {"id": cart_id, "name": name, "description": description}
        rows = self._run_write_with_retry(cypher, params)
        return rows[0]["c"] if rows else None

    def replace_cart_memories(self, cart_id: str, memory_ids: List[str]) -> None:
        """Replace the cart's :CONTAINS edges with the provided memory_ids."""
        cypher = """
        MATCH (c:MemoryCart {id: $cart_id})
        OPTIONAL MATCH (c)-[r:CONTAINS]->(:Memory)
        DELETE r
        WITH c
        UNWIND $memory_ids AS mid
        MATCH (m:Memory {id: mid})
        MERGE (c)-[:CONTAINS]->(m)
        RETURN count(m) AS added
        """
        self._run_write_with_retry(cypher, {"cart_id": cart_id, "memory_ids": memory_ids})

    def add_cart_memories(self, cart_id: str, memory_ids: List[str]) -> None:
        """Add memories to the cart (idempotent merge)."""
        if not memory_ids:
            return
        cypher = """
        MATCH (c:MemoryCart {id: $cart_id})
        UNWIND $memory_ids AS mid
        MATCH (m:Memory {id: mid})
        MERGE (c)-[:CONTAINS]->(m)
        RETURN count(m) AS added
        """
        self._run_write_with_retry(cypher, {"cart_id": cart_id, "memory_ids": memory_ids})

    def touch_cart(self, cart_id: str) -> None:
        """Update the cart's updated_at timestamp."""
        self._run_write_with_retry(
            "MATCH (c:MemoryCart {id: $id}) SET c.updated_at = datetime()",
            {"id": cart_id},
        )

    # ─── Dashboard stats ────────────────────────────────────────────────────

    def dashboard_stats(self) -> Dict[str, Any]:
        cypher = """
        -- experiments stats are synthetic (no :Experiment node)
        WITH 0 AS total, 0 AS completed, 0 AS failed

        OPTIONAL MATCH (k:Knowledge)
        WITH total, completed, failed, count(DISTINCT k.source_file) AS documents

        OPTIONAL MATCH (c:KnowledgeChunk)
        WITH total, completed, failed, documents, count(c) AS chunks

        -- searches removed
        WITH total, completed, failed, documents, chunks, 0 AS searches

        OPTIONAL MATCH (m:Memory)
        WITH total, completed, failed, documents, chunks, searches, count(m) AS memories

        OPTIONAL MATCH (mc:MemoryCart)
        WITH total, completed, failed, documents, chunks, searches, memories, count(mc) AS carts

        RETURN {
            experiments: {
                total: total,
                completed: completed,
                failed: failed
            },
            documents: documents,
            chunks: chunks,
            searches: searches,
            memories: memories,
            carts: carts
        } AS stats
        """
        rows = self._run_read_with_retry(cypher, {})
        if not rows:
            empty = {
                "experiments": {"total": 0, "completed": 0, "failed": 0},
                "documents": 0,
                "chunks": 0,
                "searches": 0,
                "memories": 0,
                "carts": 0,
            }
            log_pipeline_event(logger, "dashboard.stats", "observed empty stats from neo4j", stats=empty)
            return empty
        stats = rows[0]["stats"]
        # observation: log exact numbers + full payload so user can see what neo4j produced for Dashboard stats (documents etc)
        log_pipeline_event(logger, "dashboard.stats", "observed neo4j stats for dashboard", stats=stats)
        return stats


# ─── Helpers ──────────────────────────────────────────────────────────────────

_LUCENE_SPECIAL = set('+-&|!(){}[]^"~*?:\\/')


def _escape_lucene_query(query: str) -> str:
    """Escape Lucene special characters so the raw query is treated as terms.

    For v1 we wrap each whitespace-separated token in quotes for a simple
    AND-of-terms query (good enough for short research queries).
    """
    if not query:
        return ""
    tokens: List[str] = []
    for tok in query.split():
        if not tok:
            continue
        escaped = "".join(f"\\{ch}" if ch in _LUCENE_SPECIAL else ch for ch in tok)
        tokens.append(escaped)
    return " ".join(tokens)


# ─── Module-level singleton accessor (used by api/dependencies.py) ────────────

_client: Optional[Neo4jClient] = None


def init_neo4j_client() -> Neo4jClient:
    """Initialize the module-level Neo4jClient singleton from settings."""
    global _client
    if _client is None:
        _client = Neo4jClient(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password,
            database=settings.neo4j_database,
            max_retries=settings.neo4j_max_retries,
        )
    return _client


def get_neo4j_client() -> Neo4jClient:
    if _client is None:
        return init_neo4j_client()
    return _client


def close_neo4j_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
