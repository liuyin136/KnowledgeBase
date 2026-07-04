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
from app.core.logging import get_logger
from app.models.neo4j_models import (
    Experiment,
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

    # ─── Experiment ─────────────────────────────────────────────────────────

    def create_experiment(self, exp: Experiment) -> Dict[str, Any]:
        cypher = """
        CREATE (e:Experiment {
          id: $id,
          description: $description,
          embedding_approach: $embedding_approach,
          chunk_method: $chunk_method,
          total_chunks: $total_chunks,
          avg_tokens_per_chunk: $avg_tokens_per_chunk,
          total_time_ms: $total_time_ms,
          source_file: $source_file,
          created_at: datetime($created_at),
          status: $status,
          error_code: $error_code,
          error_message: $error_message,
          hybrid_alpha: $hybrid_alpha,
          use_bm25: $use_bm25,
          use_reranker: $use_reranker,
          top_k_vector: $top_k_vector,
          top_n_rerank: $top_n_rerank,
          parent_context_levels: $parent_context_levels,
          auto_tune_weights: $auto_tune_weights,
          best_alpha: $best_alpha,
          raw_query: $raw_query,
          kind: $kind
        })
        RETURN e
        """
        params = {
            "id": exp.id,
            "description": exp.description,
            "embedding_approach": exp.embedding_approach,
            "chunk_method": exp.chunk_method,
            "total_chunks": exp.total_chunks,
            "avg_tokens_per_chunk": exp.avg_tokens_per_chunk,
            "total_time_ms": exp.total_time_ms,
            "source_file": exp.source_file,
            "created_at": exp.created_at.isoformat(),
            "status": exp.status,
            "error_code": exp.error_code,
            "error_message": exp.error_message,
            "hybrid_alpha": exp.hybrid_alpha,
            "use_bm25": exp.use_bm25,
            "use_reranker": exp.use_reranker,
            "top_k_vector": exp.top_k_vector,
            "top_n_rerank": exp.top_n_rerank,
            "parent_context_levels": exp.parent_context_levels,
            "auto_tune_weights": exp.auto_tune_weights,
            "best_alpha": exp.best_alpha,
            "raw_query": exp.raw_query,
            "kind": exp.kind,
        }
        rows = self._run_write_with_retry(cypher, params)
        return rows[0]["e"] if rows else {}

    def update_experiment_status(
        self,
        experiment_id: str,
        *,
        status: str,
        total_chunks: Optional[int] = None,
        avg_tokens_per_chunk: Optional[float] = None,
        total_time_ms: Optional[float] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        best_alpha: Optional[float] = None,
    ) -> None:
        cypher = """
        MATCH (e:Experiment {id: $id})
        SET e.status = $status,
            e.total_chunks = coalesce($total_chunks, e.total_chunks),
            e.avg_tokens_per_chunk = coalesce($avg_tokens_per_chunk, e.avg_tokens_per_chunk),
            e.total_time_ms = coalesce($total_time_ms, e.total_time_ms),
            e.error_code = $error_code,
            e.error_message = $error_message,
            e.best_alpha = coalesce($best_alpha, e.best_alpha)
        """
        params = {
            "id": experiment_id,
            "status": status,
            "total_chunks": total_chunks,
            "avg_tokens_per_chunk": avg_tokens_per_chunk,
            "total_time_ms": total_time_ms,
            "error_code": error_code,
            "error_message": error_message,
            "best_alpha": best_alpha,
        }
        self._run_write_with_retry(cypher, params)

    def get_experiment(self, experiment_id: str) -> Optional[Dict[str, Any]]:
        cypher = "MATCH (e:Experiment {id: $id}) RETURN e"
        rows = self._run_read_with_retry(cypher, {"id": experiment_id})
        return rows[0]["e"] if rows else None

    def list_experiments(
        self,
        *,
        kind: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Return (items, total). `kind` filter is optional."""
        skip = (page - 1) * page_size
        if kind and kind.lower() in ("ingest", "search"):
            cypher = """
            MATCH (e:Experiment)
            WHERE e.kind = $kind
            WITH e ORDER BY e.created_at DESC
            RETURN collect(e) AS items, count(e) AS total
            """
            rows = self._run_read_with_retry(cypher, {"kind": kind.lower()})
        else:
            cypher = """
            MATCH (e:Experiment)
            WITH e ORDER BY e.created_at DESC
            RETURN collect(e) AS items, count(e) AS total
            """
            rows = self._run_read_with_retry(cypher, {})
        if not rows:
            return [], 0
        items = rows[0].get("items", []) or []
        total = rows[0].get("total", 0) or 0
        return items[skip : skip + page_size], total

    def list_chunks_for_experiment(self, experiment_id: str) -> List[Dict[str, Any]]:
        """Return all KnowledgeChunk rows for an experiment (observability).

        For LongText experiments (no child chunks), returns the Knowledge
        parent nodes themselves (so the chunk browser still renders).
        """
        cypher = """
        MATCH (e:Experiment {id: $id})
        OPTIONAL MATCH (k:Knowledge {experiment_id: $id})
        OPTIONAL MATCH (k)-[:HAS_CHUNK]->(c:KnowledgeChunk)
        WITH e, k, c
        ORDER BY coalesce(c.chunk_index, k.chunk_index, 0)
        RETURN collect(
          CASE
            WHEN c IS NOT NULL THEN c
            ELSE k
          END
        ) AS chunks
        """
        rows = self._run_read_with_retry(cypher, {"id": experiment_id})
        if not rows:
            return []
        chunks = rows[0].get("chunks", []) or []
        # Filter out nulls (no Knowledge nodes at all)
        return [c for c in chunks if c is not None]

    def recent_experiments(self, limit: int = 5) -> List[Dict[str, Any]]:
        cypher = """
        MATCH (e:Experiment)
        RETURN e ORDER BY e.created_at DESC LIMIT $limit
        """
        return [r["e"] for r in self._run_read_with_retry(cypher, {"limit": limit})]

    def recent_searches(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Recent search experiments (kind='search')."""
        cypher = """
        MATCH (e:Experiment {kind: 'search'})
        RETURN e ORDER BY e.created_at DESC LIMIT $limit
        """
        return [r["e"] for r in self._run_read_with_retry(cypher, {"limit": limit})]

    # ─── Knowledge + KnowledgeChunk (ingest) ────────────────────────────────

    def create_knowledge(self, k: Knowledge) -> Dict[str, Any]:
        cypher = """
        CREATE (n:Knowledge {
          id: $id,
          source_file: $source_file,
          total_tokens: $total_tokens,
          embedding_method: $embedding_method,
          created_at: datetime($created_at),
          experiment_id: $experiment_id,
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
            "experiment_id": k.experiment_id,
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
          section: $section,
          experiment_id: $experiment_id
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
            "experiment_id": c.experiment_id,
        }
        rows = self._run_write_with_retry(cypher, params)
        return rows[0]["c"] if rows else {}

    def list_documents(self, page: int = 1, page_size: int = 20) -> Tuple[List[Dict[str, Any]], int]:
        """Logical documents (one per unique source_file across all experiments).

        Returns the first-seen Knowledge node per source_file (preferring
        upload-time placeholders so size/createdAt reflect the upload, not a
        later ingest run).
        """
        skip = (page - 1) * page_size
        cypher = """
        MATCH (k:Knowledge)
        WITH k.source_file AS source_file,
             head(collect(k)) AS first,
             count(k) AS chunk_count
        RETURN collect({
          id: source_file,
          filename: source_file,
          contentType: 'text/markdown',
          sizeBytes: size(first.text),
          totalChunks: chunk_count,
          createdAt: first.created_at
        }) AS items, count(DISTINCT source_file) AS total
        """
        rows = self._run_read_with_retry(cypher, {})
        if not rows:
            return [], 0
        items = rows[0].get("items", []) or []
        total = rows[0].get("total", 0) or 0
        # Sort by createdAt desc (Neo4j collect() preserves encounter order — re-sort client-side)
        items_sorted = sorted(items, key=lambda x: x.get("createdAt", ""), reverse=True)
        return items_sorted[skip : skip + page_size], total

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
        """Delete all Knowledge + cascading KnowledgeChunk nodes for a source file.

        Removes upload-time placeholders AND any ingest-time Knowledge nodes
        (and their child KnowledgeChunks via HAS_CHUNK) for the source file.
        Returns the count of deleted Knowledge nodes.
        """
        cypher = """
        MATCH (k:Knowledge {source_file: $source_file})
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
          experiment_id: $experiment_id,
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
            "experiment_id": q.experiment_id,
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
        experiment_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Vector search on :KnowledgeChunk (the child retrieval targets).

        Returns rows with chunk + parent metadata for orchestrator scoring.
        """
        cypher = """
        CALL db.index.vector.queryNodes('knowledgechunk_vector', $top_k, $vector)
        YIELD node, score
        WHERE node:KnowledgeChunk
        MATCH (parent:Knowledge)-[:HAS_CHUNK]->(node)
        OPTIONAL MATCH (e:Experiment {id: node.experiment_id})
        WHERE $experiment_id IS NULL OR node.experiment_id = $experiment_id
        RETURN node AS chunk,
               parent AS parent,
               score AS vector_score,
               coalesce(e.id, parent.experiment_id) AS experiment_id
        ORDER BY score DESC
        LIMIT $top_k
        """
        params = {"top_k": top_k, "vector": list(query_vector), "experiment_id": experiment_id}
        return self._run_read_with_retry(cypher, params)

    def vector_search_parents(
        self,
        query_vector: List[float],
        top_k: int,
        experiment_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Vector search on :Knowledge parent nodes (used by LongText path)."""
        cypher = """
        CALL db.index.vector.queryNodes('knowledge_vector', $top_k, $vector)
        YIELD node, score
        WHERE node:Knowledge
        MATCH (e:Experiment {id: node.experiment_id})
        WHERE $experiment_id IS NULL OR node.experiment_id = $experiment_id
        RETURN node AS parent,
               score AS vector_score,
               e.id AS experiment_id
        ORDER BY score DESC
        LIMIT $top_k
        """
        params = {"top_k": top_k, "vector": list(query_vector), "experiment_id": experiment_id}
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
               score AS bm25_score,
               parent.experiment_id AS experiment_id
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
               score AS bm25_score,
               node.experiment_id AS experiment_id
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
          reranker_score: $reranker_score,
          experiment_id: $experiment_id
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
            "experiment_id": m.experiment_id,
        }
        rows = self._run_write_with_retry(cypher, params)
        return rows[0]["m"] if rows else {}

    def list_memories(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        experiment_id: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        skip = (page - 1) * page_size
        if experiment_id:
            cypher = """
            MATCH (m:Memory)
            WHERE m.experiment_id = $experiment_id
            OPTIONAL MATCH (cart:MemoryCart)-[:CONTAINS]->(m)
            WITH m, cart
            ORDER BY m.timestamp DESC
            RETURN collect({
              memory: m,
              selected: cart IS NOT NULL
            }) AS items, count(m) AS total
            """
            rows = self._run_read_with_retry(cypher, {"experiment_id": experiment_id})
        else:
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
        """Counts for the dashboard stat cards.

        `documents` = count of DISTINCT source_files (matches the v1 sandbox
        semantics where documents = unique uploaded files, not the number of
        :Knowledge nodes which can be >1 per file for LongText multi-window).
        """
        cypher = """
        MATCH (e:Experiment)
        WITH count(e) AS total,
             sum(CASE WHEN e.status = 'completed' THEN 1 ELSE 0 END) AS completed,
             sum(CASE WHEN e.status = 'failed' THEN 1 ELSE 0 END) AS failed
        MATCH (k:Knowledge)
        WITH total, completed, failed, count(DISTINCT k.source_file) AS documents
        OPTIONAL MATCH (c:KnowledgeChunk)
        WITH total, completed, failed, documents, count(c) AS chunks
        OPTIONAL MATCH (s:Experiment {kind: 'search'})
        WITH total, completed, failed, documents, chunks, count(s) AS searches
        OPTIONAL MATCH (m:Memory)
        WITH total, completed, failed, documents, chunks, searches, count(m) AS memories
        OPTIONAL MATCH (mc:MemoryCart)
        RETURN {
          experiments: {total: total, completed: completed, failed: failed},
          documents: documents,
          chunks: chunks,
          searches: searches,
          memories: memories,
          carts: count(mc)
        } AS stats
        """
        rows = self._run_read_with_retry(cypher, {})
        if not rows:
            return {
                "experiments": {"total": 0, "completed": 0, "failed": 0},
                "documents": 0,
                "chunks": 0,
                "searches": 0,
                "memories": 0,
                "carts": 0,
            }
        return rows[0]["stats"]


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
