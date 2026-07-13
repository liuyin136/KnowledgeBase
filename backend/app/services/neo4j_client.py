from __future__ import annotations

import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterable

from neo4j import Driver, GraphDatabase, ManagedTransaction, Session

from app.core.constants import (
    CHILD_COARSE_INDEX_NAMES,
    COARSE_INDEX_NAMES,
    FAMILY_COARSE_INDEX_NAMES,
    GRANDCHILD_COARSE_INDEX_NAMES,
    NEO4J_MAX_RETRIES,
    PARENT_COARSE_INDEX_NAMES,
)
from app.core.exceptions import Neo4jError
from app.services.ingest_guard import assert_ingestible_source
from app.core.logging import get_logger
from app.models.neo4j_models import (
    Knowledge,
    KnowledgeChild,
    KnowledgeChunk,
    KnowledgeFamily,
    KnowledgeGrandchild,
    KnowledgeParent,
    node_to_dict,
)

logger = get_logger("rag.db.neo4j")

_TRANSIENT = (
    "Neo.TransientError",
    "ServiceUnavailable",
    "DatabaseUnavailable",
)


def _is_transient(exc: Exception) -> bool:
    msg = str(exc)
    return any(p in msg for p in _TRANSIENT) or isinstance(exc, (ConnectionError, TimeoutError, OSError))


class Neo4jClient:
    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str = "neo4j",
    ) -> None:
        self._uri = uri or os.environ.get("NEO4J_URI", "bolt://neo4j:7687")
        self._user = user or os.environ.get("NEO4J_USER", "neo4j")
        self._password = password or os.environ.get("NEO4J_PASSWORD", "P@ssw0rd")
        self._database = database
        self._driver: Driver = GraphDatabase.driver(
            self._uri, auth=(self._user, self._password), max_connection_pool_size=50
        )

    def verify_connectivity(self) -> None:
        try:
            self._driver.verify_connectivity()
        except Exception as exc:
            raise Neo4jError(f"Neo4j unreachable: {exc}", stage="neo4j_connectivity") from exc

    def close(self) -> None:
        try:
            self._driver.close()
        except Exception:
            pass

    @contextmanager
    def session(self) -> Iterable[Session]:
        sess = self._driver.session(database=self._database)
        try:
            yield sess
        finally:
            sess.close()

    def _run_write(self, cypher: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        last_exc: Exception | None = None
        for attempt in range(NEO4J_MAX_RETRIES + 1):
            try:
                with self.session() as sess:

                    def _tx(txn: ManagedTransaction):
                        return [r.data() for r in txn.run(cypher, params)]

                    return sess.execute_write(_tx)
            except Exception as exc:
                last_exc = exc
                if _is_transient(exc) and attempt < NEO4J_MAX_RETRIES:
                    time.sleep(0.25 * (2**attempt))
                    continue
                raise Neo4jError(str(exc), stage="neo4j_write") from exc
        raise Neo4jError(str(last_exc), stage="neo4j_write")

    def _run_read(self, cypher: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        last_exc: Exception | None = None
        for attempt in range(NEO4J_MAX_RETRIES + 1):
            try:
                with self.session() as sess:

                    def _tx(txn: ManagedTransaction):
                        return [r.data() for r in txn.run(cypher, params)]

                    return sess.execute_read(_tx)
            except Exception as exc:
                last_exc = exc
                if _is_transient(exc) and attempt < NEO4J_MAX_RETRIES:
                    time.sleep(0.25 * (2**attempt))
                    continue
                raise Neo4jError(str(exc), stage="neo4j_read") from exc
        raise Neo4jError(str(last_exc), stage="neo4j_read")

    def _log_query(self, stage: str, cypher: str) -> None:
        preview = " ".join(cypher.split())[:120]
        logger.debug("neo4j_query", stage=stage, cypher_preview=preview)

    def get_knowledge_by_source(self, source_file: str) -> dict[str, Any] | None:
        rows = self._run_read(
            "MATCH (k:Knowledge {source_file: $sf}) RETURN k LIMIT 1",
            {"sf": source_file},
        )
        if not rows:
            return None
        return node_to_dict(rows[0]["k"])

    def get_existing_chunks(self, source_file: str) -> dict[int, dict[str, Any]]:
        rows = self._run_read(
            """
            MATCH (k:Knowledge {source_file: $sf})-[:HAS_CHUNK]->(c:KnowledgeChunk)
            RETURN c.chunk_index AS idx, c.content_hash AS content_hash, c.id AS id
            """,
            {"sf": source_file},
        )
        return {int(r["idx"]): r for r in rows}

    def upsert_knowledge(
        self,
        knowledge: Knowledge,
        chunks: list[KnowledgeChunk],
        *,
        skip_indices: set[int] | None = None,
        existing_indices: set[int] | None = None,
        link_log_file: bool = True,
    ) -> dict[str, int]:
        assert_ingestible_source(knowledge.source_file)
        skip_indices = skip_indices or set()
        existing_indices = existing_indices or set()
        now = datetime.now(timezone.utc).isoformat()
        parent_id = knowledge.id

        if link_log_file:
            self._run_write(
                """
                MERGE (k:Knowledge {source_file: $source_file})
                ON CREATE SET k.id = $id
                SET k.title = $title,
                    k.category = $category,
                    k.token_count = $token_count,
                    k.chunk_count = $chunk_count,
                    k.indexed_at = datetime($indexed_at),
                    k.last_content_hash = $last_content_hash,
                    k.mtime = $mtime
                WITH k
                MERGE (lf:LogFile {path: $source_file})
                ON CREATE SET lf.category = $category,
                              lf.title = $title,
                              lf.mtime = $mtime
                ON MATCH SET lf.mtime = $mtime
                MERGE (lf)-[:INDEXED_AS]->(k)
                RETURN k.id AS id
                """,
                {
                    "id": parent_id,
                    "source_file": knowledge.source_file,
                    "title": knowledge.title,
                    "category": knowledge.category,
                    "token_count": knowledge.token_count,
                    "chunk_count": knowledge.chunk_count,
                    "indexed_at": now,
                    "last_content_hash": knowledge.last_content_hash,
                    "mtime": knowledge.mtime,
                },
            )
        else:
            self._run_write(
                """
                MERGE (k:Knowledge {source_file: $source_file})
                ON CREATE SET k.id = $id
                SET k.title = $title,
                    k.category = $category,
                    k.token_count = $token_count,
                    k.chunk_count = $chunk_count,
                    k.indexed_at = datetime($indexed_at),
                    k.last_content_hash = $last_content_hash,
                    k.mtime = $mtime
                RETURN k.id AS id
                """,
                {
                    "id": parent_id,
                    "source_file": knowledge.source_file,
                    "title": knowledge.title,
                    "category": knowledge.category,
                    "token_count": knowledge.token_count,
                    "chunk_count": knowledge.chunk_count,
                    "indexed_at": now,
                    "last_content_hash": knowledge.last_content_hash,
                    "mtime": knowledge.mtime,
                },
            )

        written = updated = skipped = 0
        active_indices: set[int] = set()

        for chunk in chunks:
            active_indices.add(chunk.chunk_index)
            if chunk.chunk_index in skip_indices:
                skipped += 1
                continue

            self._run_write(
                """
                MATCH (k:Knowledge {source_file: $source_file})
                OPTIONAL MATCH (k)-[:HAS_CHUNK]->(old:KnowledgeChunk {chunk_index: $chunk_index})
                DETACH DELETE old
                CREATE (c:KnowledgeChunk {
                  id: $id,
                  chunk_index: $chunk_index,
                  content: $content,
                  content_hash: $content_hash,
                  token_count: $token_count,
                  start_token: $start_token,
                  end_token: $end_token,
                  vector: $vector,
                  vector_coarse_256: $vector_coarse_256,
                  vector_coarse_512: $vector_coarse_512,
                  embedding_model: $embedding_model,
                  indexed_at: datetime($indexed_at)
                })
                MERGE (k)-[:HAS_CHUNK]->(c)
                RETURN c.id AS id
                """,
                {
                    "source_file": knowledge.source_file,
                    "id": chunk.id,
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                    "content_hash": chunk.content_hash,
                    "token_count": chunk.token_count,
                    "start_token": chunk.start_token,
                    "end_token": chunk.end_token,
                    "vector": chunk.vector,
                    "vector_coarse_256": chunk.vector_coarse_256,
                    "vector_coarse_512": chunk.vector_coarse_512,
                    "embedding_model": chunk.embedding_model,
                    "indexed_at": now,
                },
            )
            written += 1
            if chunk.chunk_index in existing_indices:
                updated += 1

        rows = self._run_write(
            """
            MATCH (k:Knowledge {source_file: $source_file})-[:HAS_CHUNK]->(c:KnowledgeChunk)
            WHERE NOT c.chunk_index IN $active
            DETACH DELETE c
            RETURN count(c) AS deleted
            """,
            {"source_file": knowledge.source_file, "active": list(active_indices)},
        )
        deleted = rows[0]["deleted"] if rows else 0
        return {"chunks_written": written, "chunks_skipped": skipped, "chunks_updated": updated, "deleted_orphans": deleted}

    def delete_knowledge_by_source(self, source_file: str) -> int:
        """DETACH DELETE Knowledge and its chunks for a source_file. Returns chunks deleted."""
        rows = self._run_write(
            """
            OPTIONAL MATCH (k:Knowledge {source_file: $source_file})-[:HAS_CHUNK]->(c:KnowledgeChunk)
            WITH k, collect(c) AS chunks
            FOREACH (c IN chunks | DETACH DELETE c)
            WITH k, size(chunks) AS deleted
            FOREACH (_ IN CASE WHEN k IS NULL THEN [] ELSE [1] END | DETACH DELETE k)
            RETURN deleted
            """,
            {"source_file": source_file},
        )
        return int(rows[0]["deleted"]) if rows else 0

    def delete_knowledge_by_prefix(self, prefix: str) -> dict[str, int]:
        """Delete Knowledge nodes whose source_file starts with prefix."""
        rows = self._run_write(
            """
            MATCH (k:Knowledge)
            WHERE k.source_file STARTS WITH $prefix
            OPTIONAL MATCH (k)-[:HAS_CHUNK]->(c:KnowledgeChunk)
            WITH collect(DISTINCT k) AS ks, collect(DISTINCT c) AS cs
            FOREACH (n IN cs | DETACH DELETE n)
            FOREACH (n IN ks | DETACH DELETE n)
            RETURN size(ks) AS knowledge_deleted, size(cs) AS chunks_deleted
            """,
            {"prefix": prefix},
        )
        if not rows:
            return {"knowledge_deleted": 0, "chunks_deleted": 0}
        return {
            "knowledge_deleted": int(rows[0]["knowledge_deleted"]),
            "chunks_deleted": int(rows[0]["chunks_deleted"]),
        }

    def count_knowledge_by_prefix(self, prefix: str) -> int:
        rows = self._run_read(
            """
            MATCH (k:Knowledge)
            WHERE k.source_file STARTS WITH $prefix
            RETURN count(k) AS cnt
            """,
            {"prefix": prefix},
        )
        return int(rows[0]["cnt"]) if rows else 0

    def rename_knowledge_by_folder_prefix(self, old_slug: str, new_slug: str) -> int:
        """Migrate all Knowledge nodes under old_slug/ to new_slug/ and update category."""
        old_prefix = f"{old_slug}/"
        new_prefix = f"{new_slug}/"
        conflict = self._run_read(
            """
            MATCH (k:Knowledge)
            WHERE k.source_file STARTS WITH $new_prefix
            RETURN k.source_file AS sf LIMIT 1
            """,
            {"new_prefix": new_prefix},
        )
        if conflict:
            existing_under_new = self._run_read(
                """
                MATCH (k:Knowledge)
                WHERE k.source_file STARTS WITH $old_prefix
                RETURN k.source_file AS sf
                """,
                {"old_prefix": old_prefix},
            )
            old_paths = {r["sf"] for r in existing_under_new}
            for row in conflict:
                new_sf = row["sf"]
                expected_old = old_prefix + new_sf[len(new_prefix) :]
                if expected_old not in old_paths:
                    raise Neo4jError(
                        f"Knowledge already exists at source_file: {new_sf}",
                        stage="rename_knowledge_by_folder_prefix",
                    )
        rows = self._run_write(
            """
            MATCH (k:Knowledge)
            WHERE k.source_file STARTS WITH $old_prefix
            SET k.source_file = $new_prefix + substring(k.source_file, size($old_prefix)),
                k.category = $new_slug
            RETURN count(k) AS migrated
            """,
            {"old_prefix": old_prefix, "new_prefix": new_prefix, "new_slug": new_slug},
        )
        return int(rows[0]["migrated"]) if rows else 0

    def rename_knowledge_source(
        self, old_source: str, new_source: str, *, category: str
    ) -> bool:
        """Migrate Knowledge node from old to new source_file. Returns True if migrated."""
        assert_ingestible_source(old_source)
        assert_ingestible_source(new_source)
        conflict = self._run_read(
            """
            OPTIONAL MATCH (existing:Knowledge {source_file: $new})
            RETURN existing.id AS id
            """,
            {"new": new_source},
        )
        if conflict and conflict[0].get("id"):
            old_row = self.get_knowledge_by_source(old_source)
            if not old_row or old_row.get("id") != conflict[0]["id"]:
                raise Neo4jError(
                    f"Knowledge already exists at source_file: {new_source}",
                    stage="rename_knowledge_source",
                )
        rows = self._run_write(
            """
            MATCH (k:Knowledge {source_file: $old})
            SET k.source_file = $new, k.category = $category
            RETURN count(k) AS migrated
            """,
            {"old": old_source, "new": new_source, "category": category},
        )
        return bool(rows and int(rows[0]["migrated"]) > 0)

    def delete_ingestion_tree_for_source(self, source_file: str) -> dict[str, int]:
        """Purge v1.6 tree, legacy chunks, Knowledge root, and LogFile for one source."""
        tree_stats = self.delete_knowledge_tree_for_source(source_file)
        legacy_deleted = self.delete_legacy_chunks_for_source(source_file)
        k_rows = self._run_write(
            """
            MATCH (k:Knowledge {source_file: $source_file})
            WITH collect(k) AS nodes
            FOREACH (n IN nodes | DETACH DELETE n)
            RETURN size(nodes) AS deleted
            """,
            {"source_file": source_file},
        )
        lf_rows = self._run_write(
            """
            MATCH (lf:LogFile {path: $source_file})
            WITH collect(lf) AS nodes
            FOREACH (n IN nodes | DETACH DELETE n)
            RETURN size(nodes) AS deleted
            """,
            {"source_file": source_file},
        )
        return {
            **tree_stats,
            "legacy_chunks_deleted": legacy_deleted,
            "knowledge_deleted": int(k_rows[0]["deleted"]) if k_rows else 0,
            "logfile_deleted": int(lf_rows[0]["deleted"]) if lf_rows else 0,
        }

    def delete_all_vault_ingestion(self, source_files: list[str]) -> dict[str, int]:
        """Purge complete ingestion state for vault paths plus benchmark prefix."""
        totals: dict[str, int] = {}
        for source_file in source_files:
            stats = self.delete_ingestion_tree_for_source(source_file)
            for key, value in stats.items():
                totals[key] = totals.get(key, 0) + int(value)
        bench = self.delete_knowledge_by_prefix("_benchmark/")
        totals["benchmark_knowledge_deleted"] = bench["knowledge_deleted"]
        totals["benchmark_chunks_deleted"] = bench["chunks_deleted"]
        return totals

    _INGESTION_LABELS = (
        "Knowledgechunk_grand",
        "Knowledgechunk_sen",
        "Knowledgechunk",
        "Knowledgechunk_family",
        "KnowledgeChunk",
        "Knowledge",
        "LogFile",
    )

    def delete_all_ingestion(self) -> dict[str, int]:
        """Global wipe of all ingestion-related nodes (v1.6 + legacy + LogFile)."""
        label_filter = " OR ".join(f"n:{label}" for label in self._INGESTION_LABELS)
        count_rows = self._run_read(
            f"""
            MATCH (n)
            WHERE {label_filter}
            RETURN labels(n)[0] AS label, count(n) AS cnt
            """,
            {},
        )
        counts = {str(r["label"]): int(r["cnt"]) for r in count_rows}
        self._run_write(
            f"""
            MATCH (n)
            WHERE {label_filter}
            DETACH DELETE n
            """,
            {},
        )
        return counts

    def delete_all_knowledge(self) -> dict[str, int]:
        """Deprecated: prefer delete_all_ingestion(). Kept for backward compatibility."""
        stats = self.delete_all_ingestion()
        return {
            "knowledge_deleted": stats.get("Knowledge", 0),
            "chunks_deleted": stats.get("KnowledgeChunk", 0),
        }

    def vector_search_coarse_chunks(
        self,
        coarse_dim: int,
        query_vector: list[float],
        top_k: int,
        allowed_paths: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if allowed_paths is not None and len(allowed_paths) == 0:
            return []
        index_name = COARSE_INDEX_NAMES[coarse_dim]
        path_clause = ""
        params: dict[str, Any] = {"top_k": top_k, "vector": list(query_vector)}
        if allowed_paths is not None:
            path_clause = "AND parent.source_file IN $allowed_paths"
            params["allowed_paths"] = allowed_paths
        cypher = f"""
        CALL db.index.vector.queryNodes('{index_name}', $top_k, $vector)
        YIELD node, score
        WHERE node:KnowledgeChunk
        MATCH (parent:Knowledge)-[:HAS_CHUNK]->(node)
        WHERE NOT parent.source_file STARTS WITH '_benchmark/'
        {path_clause}
        RETURN node AS chunk, parent AS parent, score AS vector_score
        ORDER BY score DESC
        LIMIT $top_k
        """
        self._log_query("vector_search_coarse", cypher)
        return self._run_read(cypher, params)

    def bm25_search_chunks(
        self,
        query: str,
        top_k: int,
        allowed_paths: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if allowed_paths is not None and len(allowed_paths) == 0:
            return []
        path_clause = ""
        params: dict[str, Any] = {"q": query, "top_k": top_k}
        if allowed_paths is not None:
            path_clause = "AND parent.source_file IN $allowed_paths"
            params["allowed_paths"] = allowed_paths
        cypher = f"""
        CALL db.index.fulltext.queryNodes('knowledgechunk_text', $q)
        YIELD node, score
        WHERE node:KnowledgeChunk
        MATCH (parent:Knowledge)-[:HAS_CHUNK]->(node)
        WHERE NOT parent.source_file STARTS WITH '_benchmark/'
        {path_clause}
        RETURN node AS chunk, parent AS parent, score AS bm25_score
        ORDER BY score DESC
        LIMIT $top_k
        """
        self._log_query("bm25_search", cypher)
        return self._run_read(cypher, params)

    def get_chunk_vectors(self, chunk_ids: list[str]) -> dict[str, list[float]]:
        if not chunk_ids:
            return {}
        rows = self._run_read(
            """
            MATCH (c:KnowledgeChunk) WHERE c.id IN $ids
            RETURN c.id AS id, c.vector AS vector, c.content AS content,
                   c.chunk_index AS chunk_index, c.content_hash AS content_hash
            """,
            {"ids": chunk_ids},
        )
        return {r["id"]: r for r in rows}

    def get_existing_children(self, source_file: str) -> dict[str, str]:
        rows = self._run_read(
            """
            MATCH (k:Knowledge {source_file: $sf})-[:HAS_SECTION]->(:Knowledgechunk)
                  -[:HAS_CHILD]->(c:Knowledgechunk_sen)
            RETURN c.id AS id, c.content_hash AS content_hash
            """,
            {"sf": source_file},
        )
        return {r["id"]: r["content_hash"] for r in rows}

    def delete_legacy_chunks_for_source(self, source_file: str) -> int:
        rows = self._run_write(
            """
            MATCH (k:Knowledge {source_file: $source_file})-[:HAS_CHUNK]->(c:KnowledgeChunk)
            DETACH DELETE c
            RETURN count(c) AS deleted
            """,
            {"source_file": source_file},
        )
        return int(rows[0]["deleted"]) if rows else 0

    def delete_knowledge_tree_for_source(self, source_file: str) -> dict[str, int]:
        rows = self._run_write(
            """
            MATCH (k:Knowledge {source_file: $source_file})
            OPTIONAL MATCH (k)-[:HAS_FAMILY]->(f:Knowledgechunk_family)
            OPTIONAL MATCH (f)-[:HAS_SECTION]->(p:Knowledgechunk)
            OPTIONAL MATCH (k)-[:HAS_SECTION]->(p2:Knowledgechunk)
            OPTIONAL MATCH (p)-[:HAS_CHILD]->(c:Knowledgechunk_sen)
            OPTIONAL MATCH (p2)-[:HAS_CHILD]->(c2:Knowledgechunk_sen)
            OPTIONAL MATCH (c)-[:HAS_GRANDCHILD]->(g:Knowledgechunk_grand)
            OPTIONAL MATCH (c2)-[:HAS_GRANDCHILD]->(g2:Knowledgechunk_grand)
            WITH collect(DISTINCT g) + collect(DISTINCT g2) AS gs,
                 collect(DISTINCT c) + collect(DISTINCT c2) AS cs,
                 collect(DISTINCT p) + collect(DISTINCT p2) AS ps,
                 collect(DISTINCT f) AS fs
            FOREACH (n IN gs | DETACH DELETE n)
            FOREACH (n IN cs | DETACH DELETE n)
            FOREACH (n IN ps | DETACH DELETE n)
            FOREACH (n IN fs | DETACH DELETE n)
            RETURN size(gs) AS grandchildren_deleted,
                   size(cs) AS children_deleted,
                   size(ps) AS parents_deleted,
                   size(fs) AS families_deleted
            """,
            {"source_file": source_file},
        )
        if not rows:
            return {
                "parents_deleted": 0,
                "children_deleted": 0,
                "grandchildren_deleted": 0,
                "families_deleted": 0,
            }
        return {
            "parents_deleted": int(rows[0]["parents_deleted"]),
            "children_deleted": int(rows[0]["children_deleted"]),
            "grandchildren_deleted": int(rows[0]["grandchildren_deleted"]),
            "families_deleted": int(rows[0]["families_deleted"]),
        }

    def upsert_knowledge_tree(
        self,
        knowledge: Knowledge,
        parents: list[KnowledgeParent],
        children: list[KnowledgeChild],
        grandchildren: list[KnowledgeGrandchild],
        *,
        skip_child_ids: set[str] | None = None,
        link_log_file: bool = True,
    ) -> dict[str, int]:
        assert_ingestible_source(knowledge.source_file)
        skip_child_ids = skip_child_ids or set()
        now = datetime.now(timezone.utc).isoformat()
        parent_id = knowledge.id

        if link_log_file:
            self._run_write(
                """
                MERGE (k:Knowledge {source_file: $source_file})
                ON CREATE SET k.id = $id
                SET k.title = $title,
                    k.category = $category,
                    k.token_count = $token_count,
                    k.chunk_count = $chunk_count,
                    k.indexed_at = datetime($indexed_at),
                    k.last_content_hash = $last_content_hash,
                    k.mtime = $mtime
                WITH k
                MERGE (lf:LogFile {path: $source_file})
                ON CREATE SET lf.category = $category,
                              lf.title = $title,
                              lf.mtime = $mtime
                ON MATCH SET lf.mtime = $mtime
                MERGE (lf)-[:INDEXED_AS]->(k)
                RETURN k.id AS id
                """,
                {
                    "id": parent_id,
                    "source_file": knowledge.source_file,
                    "title": knowledge.title,
                    "category": knowledge.category,
                    "token_count": knowledge.token_count,
                    "chunk_count": knowledge.chunk_count,
                    "indexed_at": now,
                    "last_content_hash": knowledge.last_content_hash,
                    "mtime": knowledge.mtime,
                },
            )
        else:
            self._run_write(
                """
                MERGE (k:Knowledge {source_file: $source_file})
                ON CREATE SET k.id = $id
                SET k.title = $title,
                    k.category = $category,
                    k.token_count = $token_count,
                    k.chunk_count = $chunk_count,
                    k.indexed_at = datetime($indexed_at),
                    k.last_content_hash = $last_content_hash,
                    k.mtime = $mtime
                RETURN k.id AS id
                """,
                {
                    "id": parent_id,
                    "source_file": knowledge.source_file,
                    "title": knowledge.title,
                    "category": knowledge.category,
                    "token_count": knowledge.token_count,
                    "chunk_count": knowledge.chunk_count,
                    "indexed_at": now,
                    "last_content_hash": knowledge.last_content_hash,
                    "mtime": knowledge.mtime,
                },
            )

        parents_written = children_written = grandchildren_written = children_skipped = 0
        active_parent_ids: set[str] = set()
        active_child_ids: set[str] = set()
        active_grandchild_ids: set[str] = set()

        for parent in parents:
            active_parent_ids.add(parent.id)
            self._run_write(
                """
                MATCH (k:Knowledge {source_file: $source_file})
                OPTIONAL MATCH (k)-[:HAS_SECTION]->(old:Knowledgechunk {parent_index: $parent_index})
                DETACH DELETE old
                CREATE (p:Knowledgechunk {
                  id: $id,
                  parent_index: $parent_index,
                  content: $content,
                  content_hash: $content_hash,
                  header_path: $header_path,
                  source_file: $source_file,
                  token_count: $token_count
                })
                MERGE (k)-[:HAS_SECTION]->(p)
                RETURN p.id AS id
                """,
                {
                    "source_file": knowledge.source_file,
                    "id": parent.id,
                    "parent_index": parent.parent_index,
                    "content": parent.content,
                    "content_hash": parent.content_hash,
                    "header_path": parent.header_path,
                    "token_count": parent.token_count,
                },
            )
            parents_written += 1

        for child in children:
            active_child_ids.add(child.id)
            if child.id in skip_child_ids:
                children_skipped += 1
                continue

            self._run_write(
                """
                MATCH (p:Knowledgechunk {id: $parent_id})
                OPTIONAL MATCH (p)-[:HAS_CHILD]->(old:Knowledgechunk_sen {child_index: $child_index})
                DETACH DELETE old
                CREATE (c:Knowledgechunk_sen {
                  id: $id,
                  parent_id: $parent_id,
                  child_index: $child_index,
                  content: $content,
                  content_hash: $content_hash,
                  token_count: $token_count,
                  source_file: $source_file,
                  vector: $vector,
                  vector_coarse_256: $vector_coarse_256,
                  vector_coarse_512: $vector_coarse_512,
                  embedding_model: $embedding_model,
                  indexed_at: datetime($indexed_at)
                })
                MERGE (p)-[:HAS_CHILD]->(c)
                RETURN c.id AS id
                """,
                {
                    "parent_id": child.parent_id,
                    "id": child.id,
                    "child_index": child.child_index,
                    "content": child.content,
                    "content_hash": child.content_hash,
                    "token_count": child.token_count,
                    "source_file": child.source_file,
                    "vector": child.vector,
                    "vector_coarse_256": child.vector_coarse_256,
                    "vector_coarse_512": child.vector_coarse_512,
                    "embedding_model": child.embedding_model,
                    "indexed_at": now,
                },
            )
            children_written += 1

        for grandchild in grandchildren:
            active_grandchild_ids.add(grandchild.id)
            if grandchild.child_id in skip_child_ids:
                continue

            self._run_write(
                """
                MATCH (c:Knowledgechunk_sen {id: $child_id})
                OPTIONAL MATCH (c)-[:HAS_GRANDCHILD]->(old:Knowledgechunk_grand {grandchild_index: $grandchild_index})
                DETACH DELETE old
                CREATE (g:Knowledgechunk_grand {
                  id: $id,
                  child_id: $child_id,
                  parent_id: $parent_id,
                  grandchild_index: $grandchild_index,
                  content: $content,
                  source_file: $source_file
                })
                MERGE (c)-[:HAS_GRANDCHILD]->(g)
                RETURN g.id AS id
                """,
                {
                    "child_id": grandchild.child_id,
                    "id": grandchild.id,
                    "parent_id": grandchild.parent_id,
                    "grandchild_index": grandchild.grandchild_index,
                    "content": grandchild.content,
                    "source_file": grandchild.source_file,
                },
            )
            grandchildren_written += 1

        rows = self._run_write(
            """
            MATCH (k:Knowledge {source_file: $source_file})-[:HAS_SECTION]->(p:Knowledgechunk)
            OPTIONAL MATCH (p)-[:HAS_CHILD]->(c:Knowledgechunk_sen)
            OPTIONAL MATCH (c)-[:HAS_GRANDCHILD]->(g:Knowledgechunk_grand)
            WITH collect(DISTINCT p) AS ps, collect(DISTINCT c) AS cs, collect(DISTINCT g) AS gs
            FOREACH (n IN [x IN ps WHERE NOT x.id IN $active_parents] | DETACH DELETE n)
            FOREACH (n IN [x IN cs WHERE NOT x.id IN $active_children] | DETACH DELETE n)
            FOREACH (n IN [x IN gs WHERE NOT x.id IN $active_grandchildren] | DETACH DELETE n)
            RETURN size([x IN ps WHERE NOT x.id IN $active_parents]) AS parents_deleted,
                   size([x IN cs WHERE NOT x.id IN $active_children]) AS children_deleted,
                   size([x IN gs WHERE NOT x.id IN $active_grandchildren]) AS grandchildren_deleted
            """,
            {
                "source_file": knowledge.source_file,
                "active_parents": list(active_parent_ids),
                "active_children": list(active_child_ids),
                "active_grandchildren": list(active_grandchild_ids),
            },
        )
        deleted = rows[0] if rows else {}
        return {
            "parents_written": parents_written,
            "children_written": children_written,
            "children_skipped": children_skipped,
            "grandchildren_written": grandchildren_written,
            "parents_deleted": int(deleted.get("parents_deleted", 0)),
            "children_deleted": int(deleted.get("children_deleted", 0)),
            "grandchildren_deleted": int(deleted.get("grandchildren_deleted", 0)),
        }

    def vector_search_coarse_children(
        self,
        coarse_dim: int,
        query_vector: list[float],
        top_k: int,
        allowed_paths: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if allowed_paths is not None and len(allowed_paths) == 0:
            return []
        index_name = CHILD_COARSE_INDEX_NAMES[coarse_dim]
        path_clause = ""
        params: dict[str, Any] = {"top_k": top_k, "vector": list(query_vector)}
        if allowed_paths is not None:
            path_clause = "AND doc.source_file IN $allowed_paths"
            params["allowed_paths"] = allowed_paths
        cypher = f"""
        CALL db.index.vector.queryNodes('{index_name}', $top_k, $vector)
        YIELD node, score
        WHERE node:Knowledgechunk_sen
        MATCH (parent:Knowledgechunk)-[:HAS_CHILD]->(node)
        MATCH (doc:Knowledge)-[:HAS_SECTION]->(parent)
        WHERE NOT doc.source_file STARTS WITH '_benchmark/'
        {path_clause}
        RETURN node AS child, parent AS parent, score AS vector_score
        ORDER BY score DESC
        LIMIT $top_k
        """
        self._log_query("vector_search_coarse_children", cypher)
        return self._run_read(cypher, params)

    def bm25_search_children(
        self,
        query: str,
        top_k: int,
        allowed_paths: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if allowed_paths is not None and len(allowed_paths) == 0:
            return []
        path_clause = ""
        params: dict[str, Any] = {"q": query, "top_k": top_k}
        if allowed_paths is not None:
            path_clause = "AND doc.source_file IN $allowed_paths"
            params["allowed_paths"] = allowed_paths
        cypher = f"""
        CALL db.index.fulltext.queryNodes('knowledgechunk_sen_text', $q)
        YIELD node, score
        WHERE node:Knowledgechunk_sen
        MATCH (parent:Knowledgechunk)-[:HAS_CHILD]->(node)
        MATCH (doc:Knowledge)-[:HAS_SECTION]->(parent)
        WHERE NOT doc.source_file STARTS WITH '_benchmark/'
        {path_clause}
        RETURN node AS child, parent AS parent, score AS bm25_score
        ORDER BY score DESC
        LIMIT $top_k
        """
        self._log_query("bm25_search_children", cypher)
        return self._run_read(cypher, params)

    def get_child_vectors(self, child_ids: list[str]) -> dict[str, list[float]]:
        if not child_ids:
            return {}
        rows = self._run_read(
            """
            MATCH (c:Knowledgechunk_sen) WHERE c.id IN $ids
            RETURN c.id AS id, c.vector AS vector, c.content AS content,
                   c.child_index AS child_index, c.content_hash AS content_hash,
                   c.parent_id AS parent_id
            """,
            {"ids": child_ids},
        )
        return {r["id"]: r for r in rows}

    def get_parents_by_child_ids(self, child_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not child_ids:
            return {}
        rows = self._run_read(
            """
            MATCH (p:Knowledgechunk)-[:HAS_CHILD]->(c:Knowledgechunk_sen)
            WHERE c.id IN $ids
            RETURN DISTINCT p.id AS parent_id, p.content AS content,
                   p.header_path AS header_path, p.source_file AS source_file
            """,
            {"ids": child_ids},
        )
        return {
            r["parent_id"]: {
                "content": r["content"],
                "header_path": r["header_path"],
                "source_file": r["source_file"],
            }
            for r in rows
        }

    def get_grandchildren_for_children(self, child_ids: list[str]) -> list[dict[str, Any]]:
        if not child_ids:
            return []
        return self._run_read(
            """
            MATCH (c:Knowledgechunk_sen)-[:HAS_GRANDCHILD]->(g:Knowledgechunk_grand)
            WHERE c.id IN $ids
            RETURN g.id AS id, g.child_id AS child_id, g.parent_id AS parent_id,
                   g.content AS content, g.grandchild_index AS grandchild_index
            ORDER BY g.grandchild_index
            """,
            {"ids": child_ids},
        )

    def upsert_knowledge_tree_v162(
        self,
        knowledge: Knowledge,
        families: list[KnowledgeFamily],
        parents: list[KnowledgeParent],
        children: list[KnowledgeChild],
        grandchildren: list[KnowledgeGrandchild],
        *,
        link_log_file: bool = True,
    ) -> dict[str, int]:
        """Upsert 4-tier Family→Parent→Child→Grandchild tree with vectors on all tiers."""
        assert_ingestible_source(knowledge.source_file)
        now = datetime.now(timezone.utc).isoformat()
        self.delete_knowledge_tree_for_source(knowledge.source_file)
        self.delete_legacy_chunks_for_source(knowledge.source_file)

        if link_log_file:
            self._run_write(
                """
                MERGE (k:Knowledge {source_file: $source_file})
                ON CREATE SET k.id = $id
                SET k.title = $title,
                    k.category = $category,
                    k.token_count = $token_count,
                    k.chunk_count = $chunk_count,
                    k.indexed_at = datetime($indexed_at),
                    k.last_content_hash = $last_content_hash,
                    k.mtime = $mtime
                WITH k
                MERGE (lf:LogFile {path: $source_file})
                ON CREATE SET lf.category = $category,
                              lf.title = $title,
                              lf.mtime = $mtime
                ON MATCH SET lf.mtime = $mtime
                MERGE (lf)-[:INDEXED_AS]->(k)
                RETURN k.id AS id
                """,
                {
                    "id": knowledge.id,
                    "source_file": knowledge.source_file,
                    "title": knowledge.title,
                    "category": knowledge.category,
                    "token_count": knowledge.token_count,
                    "chunk_count": knowledge.chunk_count,
                    "indexed_at": now,
                    "last_content_hash": knowledge.last_content_hash,
                    "mtime": knowledge.mtime,
                },
            )
        else:
            self._run_write(
                """
                MERGE (k:Knowledge {source_file: $source_file})
                ON CREATE SET k.id = $id
                SET k.title = $title,
                    k.category = $category,
                    k.token_count = $token_count,
                    k.chunk_count = $chunk_count,
                    k.indexed_at = datetime($indexed_at),
                    k.last_content_hash = $last_content_hash,
                    k.mtime = $mtime
                RETURN k.id AS id
                """,
                {
                    "id": knowledge.id,
                    "source_file": knowledge.source_file,
                    "title": knowledge.title,
                    "category": knowledge.category,
                    "token_count": knowledge.token_count,
                    "chunk_count": knowledge.chunk_count,
                    "indexed_at": now,
                    "last_content_hash": knowledge.last_content_hash,
                    "mtime": knowledge.mtime,
                },
            )

        families_written = parents_written = children_written = grandchildren_written = 0

        for fam in families:
            self._run_write(
                """
                MATCH (k:Knowledge {source_file: $source_file})
                CREATE (f:Knowledgechunk_family {
                  id: $id,
                  family_index: $family_index,
                  content: $content,
                  content_hash: $content_hash,
                  source_file: $source_file,
                  token_count: $token_count,
                  vector: $vector,
                  vector_coarse_256: $vector_coarse_256,
                  vector_coarse_512: $vector_coarse_512,
                  embedding_model: $embedding_model,
                  indexed_at: datetime($indexed_at)
                })
                MERGE (k)-[:HAS_FAMILY]->(f)
                RETURN f.id AS id
                """,
                {
                    "source_file": knowledge.source_file,
                    "id": fam.id,
                    "family_index": fam.family_index,
                    "content": fam.content,
                    "content_hash": fam.content_hash,
                    "token_count": fam.token_count,
                    "vector": fam.vector,
                    "vector_coarse_256": fam.vector_coarse_256,
                    "vector_coarse_512": fam.vector_coarse_512,
                    "embedding_model": fam.embedding_model,
                    "indexed_at": now,
                },
            )
            families_written += 1

        for parent in parents:
            family_id = parent.family_id or (families[0].id if families else "")
            self._run_write(
                """
                MATCH (f:Knowledgechunk_family {id: $family_id})
                CREATE (p:Knowledgechunk {
                  id: $id,
                  parent_index: $parent_index,
                  content: $content,
                  content_hash: $content_hash,
                  header_path: $header_path,
                  source_file: $source_file,
                  family_id: $family_id,
                  token_count: $token_count,
                  vector: $vector,
                  vector_coarse_256: $vector_coarse_256,
                  vector_coarse_512: $vector_coarse_512,
                  embedding_model: $embedding_model,
                  indexed_at: datetime($indexed_at)
                })
                MERGE (f)-[:HAS_SECTION]->(p)
                RETURN p.id AS id
                """,
                {
                    "family_id": family_id,
                    "id": parent.id,
                    "parent_index": parent.parent_index,
                    "content": parent.content,
                    "content_hash": parent.content_hash,
                    "header_path": parent.header_path,
                    "source_file": knowledge.source_file,
                    "token_count": parent.token_count,
                    "vector": parent.vector,
                    "vector_coarse_256": parent.vector_coarse_256,
                    "vector_coarse_512": parent.vector_coarse_512,
                    "embedding_model": parent.embedding_model,
                    "indexed_at": now,
                },
            )
            parents_written += 1

        for child in children:
            self._run_write(
                """
                MATCH (p:Knowledgechunk {id: $parent_id})
                CREATE (c:Knowledgechunk_sen {
                  id: $id,
                  parent_id: $parent_id,
                  child_index: $child_index,
                  content: $content,
                  content_hash: $content_hash,
                  token_count: $token_count,
                  source_file: $source_file,
                  block_type: $block_type,
                  vector: $vector,
                  vector_coarse_256: $vector_coarse_256,
                  vector_coarse_512: $vector_coarse_512,
                  embedding_model: $embedding_model,
                  indexed_at: datetime($indexed_at)
                })
                MERGE (p)-[:HAS_CHILD]->(c)
                RETURN c.id AS id
                """,
                {
                    "parent_id": child.parent_id,
                    "id": child.id,
                    "child_index": child.child_index,
                    "content": child.content,
                    "content_hash": child.content_hash,
                    "token_count": child.token_count,
                    "source_file": child.source_file,
                    "block_type": child.block_type,
                    "vector": child.vector,
                    "vector_coarse_256": child.vector_coarse_256,
                    "vector_coarse_512": child.vector_coarse_512,
                    "embedding_model": child.embedding_model,
                    "indexed_at": now,
                },
            )
            children_written += 1

        for grandchild in grandchildren:
            self._run_write(
                """
                MATCH (c:Knowledgechunk_sen {id: $child_id})
                CREATE (g:Knowledgechunk_grand {
                  id: $id,
                  child_id: $child_id,
                  parent_id: $parent_id,
                  grandchild_index: $grandchild_index,
                  content: $content,
                  content_hash: $content_hash,
                  token_count: $token_count,
                  source_file: $source_file,
                  vector: $vector,
                  vector_coarse_256: $vector_coarse_256,
                  vector_coarse_512: $vector_coarse_512,
                  embedding_model: $embedding_model,
                  indexed_at: datetime($indexed_at)
                })
                MERGE (c)-[:HAS_GRANDCHILD]->(g)
                RETURN g.id AS id
                """,
                {
                    "child_id": grandchild.child_id,
                    "id": grandchild.id,
                    "parent_id": grandchild.parent_id,
                    "grandchild_index": grandchild.grandchild_index,
                    "content": grandchild.content,
                    "content_hash": grandchild.content_hash,
                    "token_count": grandchild.token_count,
                    "source_file": grandchild.source_file,
                    "vector": grandchild.vector,
                    "vector_coarse_256": grandchild.vector_coarse_256,
                    "vector_coarse_512": grandchild.vector_coarse_512,
                    "embedding_model": grandchild.embedding_model,
                    "indexed_at": now,
                },
            )
            grandchildren_written += 1

        return {
            "families_written": families_written,
            "parents_written": parents_written,
            "children_written": children_written,
            "grandchildren_written": grandchildren_written,
        }

    def _tier_path_clauses(
        self,
        *,
        allowed_paths: list[str] | None,
        allowed_ids: list[str] | None,
        id_field: str,
    ) -> tuple[str, dict[str, Any]]:
        clauses: list[str] = []
        params: dict[str, Any] = {}
        if allowed_paths is not None:
            clauses.append("AND doc.source_file IN $allowed_paths")
            params["allowed_paths"] = allowed_paths
        if allowed_ids is not None:
            clauses.append(f"AND node.{id_field} IN $allowed_ids" if id_field == "id" else f"AND node.id IN $allowed_ids")
            # For cascade we filter by ancestor ids differently per tier — use node.id when allowed_ids set
            params["allowed_ids"] = allowed_ids
        return " ".join(clauses), params

    def vector_search_coarse_family(
        self,
        coarse_dim: int,
        query_vector: list[float],
        top_k: int,
        allowed_paths: list[str] | None = None,
        allowed_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if allowed_paths is not None and len(allowed_paths) == 0:
            return []
        if allowed_ids is not None and len(allowed_ids) == 0:
            return []
        index_name = FAMILY_COARSE_INDEX_NAMES[coarse_dim]
        params: dict[str, Any] = {"top_k": top_k, "vector": list(query_vector)}
        path_clause = ""
        if allowed_paths is not None:
            path_clause += " AND doc.source_file IN $allowed_paths"
            params["allowed_paths"] = allowed_paths
        if allowed_ids is not None:
            path_clause += " AND node.id IN $allowed_ids"
            params["allowed_ids"] = allowed_ids
        cypher = f"""
        CALL db.index.vector.queryNodes('{index_name}', $top_k, $vector)
        YIELD node, score
        WHERE node:Knowledgechunk_family
        MATCH (doc:Knowledge)-[:HAS_FAMILY]->(node)
        WHERE NOT doc.source_file STARTS WITH '_benchmark/'
        {path_clause}
        RETURN node AS family, doc AS doc, score AS vector_score
        ORDER BY score DESC
        LIMIT $top_k
        """
        self._log_query("vector_search_coarse_family", cypher)
        return self._run_read(cypher, params)

    def bm25_search_family(
        self,
        query: str,
        top_k: int,
        allowed_paths: list[str] | None = None,
        allowed_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if allowed_paths is not None and len(allowed_paths) == 0:
            return []
        if allowed_ids is not None and len(allowed_ids) == 0:
            return []
        params: dict[str, Any] = {"q": query, "top_k": top_k}
        path_clause = ""
        if allowed_paths is not None:
            path_clause += " AND doc.source_file IN $allowed_paths"
            params["allowed_paths"] = allowed_paths
        if allowed_ids is not None:
            path_clause += " AND node.id IN $allowed_ids"
            params["allowed_ids"] = allowed_ids
        cypher = f"""
        CALL db.index.fulltext.queryNodes('knowledgechunk_family_text', $q)
        YIELD node, score
        WHERE node:Knowledgechunk_family
        MATCH (doc:Knowledge)-[:HAS_FAMILY]->(node)
        WHERE NOT doc.source_file STARTS WITH '_benchmark/'
        {path_clause}
        RETURN node AS family, doc AS doc, score AS bm25_score
        ORDER BY score DESC
        LIMIT $top_k
        """
        self._log_query("bm25_search_family", cypher)
        return self._run_read(cypher, params)

    def vector_search_coarse_parents(
        self,
        coarse_dim: int,
        query_vector: list[float],
        top_k: int,
        allowed_paths: list[str] | None = None,
        allowed_family_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if allowed_paths is not None and len(allowed_paths) == 0:
            return []
        if allowed_family_ids is not None and len(allowed_family_ids) == 0:
            return []
        index_name = PARENT_COARSE_INDEX_NAMES[coarse_dim]
        params: dict[str, Any] = {"top_k": top_k, "vector": list(query_vector)}
        path_clause = ""
        if allowed_paths is not None:
            path_clause += " AND doc.source_file IN $allowed_paths"
            params["allowed_paths"] = allowed_paths
        if allowed_family_ids is not None:
            path_clause += " AND fam.id IN $allowed_family_ids"
            params["allowed_family_ids"] = allowed_family_ids
        cypher = f"""
        CALL db.index.vector.queryNodes('{index_name}', $top_k, $vector)
        YIELD node, score
        WHERE node:Knowledgechunk
        MATCH (fam:Knowledgechunk_family)-[:HAS_SECTION]->(node)
        MATCH (doc:Knowledge)-[:HAS_FAMILY]->(fam)
        WHERE NOT doc.source_file STARTS WITH '_benchmark/'
        {path_clause}
        RETURN node AS parent, fam AS family, doc AS doc, score AS vector_score
        ORDER BY score DESC
        LIMIT $top_k
        """
        self._log_query("vector_search_coarse_parents", cypher)
        return self._run_read(cypher, params)

    def bm25_search_parents(
        self,
        query: str,
        top_k: int,
        allowed_paths: list[str] | None = None,
        allowed_family_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if allowed_paths is not None and len(allowed_paths) == 0:
            return []
        if allowed_family_ids is not None and len(allowed_family_ids) == 0:
            return []
        params: dict[str, Any] = {"q": query, "top_k": top_k}
        path_clause = ""
        if allowed_paths is not None:
            path_clause += " AND doc.source_file IN $allowed_paths"
            params["allowed_paths"] = allowed_paths
        if allowed_family_ids is not None:
            path_clause += " AND fam.id IN $allowed_family_ids"
            params["allowed_family_ids"] = allowed_family_ids
        cypher = f"""
        CALL db.index.fulltext.queryNodes('knowledgechunk_parent_text', $q)
        YIELD node, score
        WHERE node:Knowledgechunk
        MATCH (fam:Knowledgechunk_family)-[:HAS_SECTION]->(node)
        MATCH (doc:Knowledge)-[:HAS_FAMILY]->(fam)
        WHERE NOT doc.source_file STARTS WITH '_benchmark/'
        {path_clause}
        RETURN node AS parent, fam AS family, doc AS doc, score AS bm25_score
        ORDER BY score DESC
        LIMIT $top_k
        """
        self._log_query("bm25_search_parents", cypher)
        return self._run_read(cypher, params)

    def vector_search_coarse_children_v162(
        self,
        coarse_dim: int,
        query_vector: list[float],
        top_k: int,
        allowed_paths: list[str] | None = None,
        allowed_parent_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if allowed_paths is not None and len(allowed_paths) == 0:
            return []
        if allowed_parent_ids is not None and len(allowed_parent_ids) == 0:
            return []
        index_name = CHILD_COARSE_INDEX_NAMES[coarse_dim]
        params: dict[str, Any] = {"top_k": top_k, "vector": list(query_vector)}
        path_clause = ""
        if allowed_paths is not None:
            path_clause += " AND doc.source_file IN $allowed_paths"
            params["allowed_paths"] = allowed_paths
        if allowed_parent_ids is not None:
            path_clause += " AND parent.id IN $allowed_parent_ids"
            params["allowed_parent_ids"] = allowed_parent_ids
        cypher = f"""
        CALL db.index.vector.queryNodes('{index_name}', $top_k, $vector)
        YIELD node, score
        WHERE node:Knowledgechunk_sen
        MATCH (parent:Knowledgechunk)-[:HAS_CHILD]->(node)
        MATCH (fam:Knowledgechunk_family)-[:HAS_SECTION]->(parent)
        MATCH (doc:Knowledge)-[:HAS_FAMILY]->(fam)
        WHERE NOT doc.source_file STARTS WITH '_benchmark/'
        {path_clause}
        RETURN node AS child, parent AS parent, fam AS family, score AS vector_score
        ORDER BY score DESC
        LIMIT $top_k
        """
        self._log_query("vector_search_coarse_children_v162", cypher)
        return self._run_read(cypher, params)

    def bm25_search_children_v162(
        self,
        query: str,
        top_k: int,
        allowed_paths: list[str] | None = None,
        allowed_parent_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if allowed_paths is not None and len(allowed_paths) == 0:
            return []
        if allowed_parent_ids is not None and len(allowed_parent_ids) == 0:
            return []
        params: dict[str, Any] = {"q": query, "top_k": top_k}
        path_clause = ""
        if allowed_paths is not None:
            path_clause += " AND doc.source_file IN $allowed_paths"
            params["allowed_paths"] = allowed_paths
        if allowed_parent_ids is not None:
            path_clause += " AND parent.id IN $allowed_parent_ids"
            params["allowed_parent_ids"] = allowed_parent_ids
        cypher = f"""
        CALL db.index.fulltext.queryNodes('knowledgechunk_sen_text', $q)
        YIELD node, score
        WHERE node:Knowledgechunk_sen
        MATCH (parent:Knowledgechunk)-[:HAS_CHILD]->(node)
        MATCH (fam:Knowledgechunk_family)-[:HAS_SECTION]->(parent)
        MATCH (doc:Knowledge)-[:HAS_FAMILY]->(fam)
        WHERE NOT doc.source_file STARTS WITH '_benchmark/'
        {path_clause}
        RETURN node AS child, parent AS parent, fam AS family, score AS bm25_score
        ORDER BY score DESC
        LIMIT $top_k
        """
        self._log_query("bm25_search_children_v162", cypher)
        return self._run_read(cypher, params)

    def vector_search_coarse_grandchildren(
        self,
        coarse_dim: int,
        query_vector: list[float],
        top_k: int,
        allowed_paths: list[str] | None = None,
        allowed_child_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if allowed_paths is not None and len(allowed_paths) == 0:
            return []
        if allowed_child_ids is not None and len(allowed_child_ids) == 0:
            return []
        index_name = GRANDCHILD_COARSE_INDEX_NAMES[coarse_dim]
        params: dict[str, Any] = {"top_k": top_k, "vector": list(query_vector)}
        path_clause = ""
        if allowed_paths is not None:
            path_clause += " AND doc.source_file IN $allowed_paths"
            params["allowed_paths"] = allowed_paths
        if allowed_child_ids is not None:
            path_clause += " AND child.id IN $allowed_child_ids"
            params["allowed_child_ids"] = allowed_child_ids
        cypher = f"""
        CALL db.index.vector.queryNodes('{index_name}', $top_k, $vector)
        YIELD node, score
        WHERE node:Knowledgechunk_grand
        MATCH (child:Knowledgechunk_sen)-[:HAS_GRANDCHILD]->(node)
        MATCH (parent:Knowledgechunk)-[:HAS_CHILD]->(child)
        MATCH (fam:Knowledgechunk_family)-[:HAS_SECTION]->(parent)
        MATCH (doc:Knowledge)-[:HAS_FAMILY]->(fam)
        WHERE NOT doc.source_file STARTS WITH '_benchmark/'
        {path_clause}
        RETURN node AS grandchild, child AS child, parent AS parent, fam AS family,
               score AS vector_score
        ORDER BY score DESC
        LIMIT $top_k
        """
        self._log_query("vector_search_coarse_grandchildren", cypher)
        return self._run_read(cypher, params)

    def bm25_search_grandchildren(
        self,
        query: str,
        top_k: int,
        allowed_paths: list[str] | None = None,
        allowed_child_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if allowed_paths is not None and len(allowed_paths) == 0:
            return []
        if allowed_child_ids is not None and len(allowed_child_ids) == 0:
            return []
        params: dict[str, Any] = {"q": query, "top_k": top_k}
        path_clause = ""
        if allowed_paths is not None:
            path_clause += " AND doc.source_file IN $allowed_paths"
            params["allowed_paths"] = allowed_paths
        if allowed_child_ids is not None:
            path_clause += " AND child.id IN $allowed_child_ids"
            params["allowed_child_ids"] = allowed_child_ids
        cypher = f"""
        CALL db.index.fulltext.queryNodes('knowledgechunk_grand_text', $q)
        YIELD node, score
        WHERE node:Knowledgechunk_grand
        MATCH (child:Knowledgechunk_sen)-[:HAS_GRANDCHILD]->(node)
        MATCH (parent:Knowledgechunk)-[:HAS_CHILD]->(child)
        MATCH (fam:Knowledgechunk_family)-[:HAS_SECTION]->(parent)
        MATCH (doc:Knowledge)-[:HAS_FAMILY]->(fam)
        WHERE NOT doc.source_file STARTS WITH '_benchmark/'
        {path_clause}
        RETURN node AS grandchild, child AS child, parent AS parent, fam AS family,
               score AS bm25_score
        ORDER BY score DESC
        LIMIT $top_k
        """
        self._log_query("bm25_search_grandchildren", cypher)
        return self._run_read(cypher, params)

    def get_node_vectors(self, label: str, ids: list[str]) -> dict[str, dict[str, Any]]:
        if not ids:
            return {}
        rows = self._run_read(
            f"""
            MATCH (n:{label}) WHERE n.id IN $ids
            RETURN n.id AS id, n.vector AS vector, n.content AS content
            """,
            {"ids": ids},
        )
        return {r["id"]: r for r in rows}

    # ─── Phase 2 GraphRAG memory ─────────────────────────────────────────────

    def get_grandchild_contents(self, grandchild_ids: list[str]) -> list[dict[str, Any]]:
        if not grandchild_ids:
            return []
        rows = self._run_read(
            """
            MATCH (g:Knowledgechunk_grand)
            WHERE g.id IN $ids
            OPTIONAL MATCH (doc:Knowledge)-[:HAS_FAMILY]->(:Knowledgechunk_family)
              -[:HAS_SECTION]->(:Knowledgechunk)-[:HAS_CHILD]->(:Knowledgechunk_sen)
              -[:HAS_GRANDCHILD]->(g)
            RETURN g.id AS id, g.content AS content, doc.source_file AS source_file
            """,
            {"ids": grandchild_ids},
        )
        by_id = {r["id"]: r for r in rows}
        ordered: list[dict[str, Any]] = []
        for gid in grandchild_ids:
            row = by_id.get(gid)
            if row:
                ordered.append(row)
        return ordered

    def get_memory_version(self, memory_key: str) -> int:
        rows = self._run_read(
            "MATCH (m:Memory {memory_key: $memory_key}) RETURN m.version AS version LIMIT 1",
            {"memory_key": memory_key},
        )
        if not rows:
            return 0
        return int(rows[0].get("version") or 0)

    def delete_memory_subgraph(self, memory_key: str) -> dict[str, int]:
        """Remove graph-memory batch nodes; does not touch v1.62 ingestion tree."""
        rows = self._run_read(
            """
            MATCH (n)
            WHERE n.memory_key = $memory_key
            RETURN labels(n)[0] AS label, count(*) AS cnt
            """,
            {"memory_key": memory_key},
        )
        stats = {r["label"]: int(r["cnt"]) for r in rows}
        self._run_write(
            """
            MATCH (n)
            WHERE n.memory_key = $memory_key
            DETACH DELETE n
            """,
            {"memory_key": memory_key},
        )
        self._run_write(
            """
            MATCH (m:Memory {memory_key: $memory_key})
            DETACH DELETE m
            """,
            {"memory_key": memory_key},
        )
        return stats

    def merge_memory_graph(
        self,
        *,
        memory_key: str,
        memory_id: str,
        query_text: str,
        user_query_id: str,
        trace_id: str | None,
        summary: str,
        grandchild_ids: list[str],
        entities: list[dict[str, Any]],
        relations: list[dict[str, Any]],
        claims: list[dict[str, Any]],
        communities: list[dict[str, Any]],
        summaries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        previous_version = self.get_memory_version(memory_key)
        self.delete_memory_subgraph(memory_key)
        version = previous_version + 1

        params: dict[str, Any] = {
            "memory_key": memory_key,
            "memory_id": memory_id,
            "query_text": query_text,
            "user_query_id": user_query_id,
            "trace_id": trace_id or "",
            "summary": summary,
            "version": version,
            "grandchild_ids": grandchild_ids,
            "entities": entities,
            "relations": relations,
            "claims": claims,
            "communities": communities,
            "summaries": summaries,
        }

        self._run_write(
            """
            MERGE (q:UserQuery {id: $user_query_id})
            ON CREATE SET q.query_text = $query_text, q.trace_id = $trace_id,
                          q.created_at = datetime()
            SET q.query_text = $query_text
            WITH q
            CREATE (m:Memory {
              memory_key: $memory_key,
              id: $memory_id,
              content: $summary,
              source_query_id: $user_query_id,
              extracted_at: datetime(),
              version: $version
            })
            MERGE (q)-[:TRIGGERED]->(m)
            WITH m
            UNWIND $grandchild_ids AS gid
            MATCH (g:Knowledgechunk_grand {id: gid})
            MERGE (m)-[:RETRIEVED]->(g)
            RETURN m.id AS memory_id, m.version AS version
            """,
            params,
        )

        if entities:
            self._run_write(
                """
                UNWIND $entities AS row
                MERGE (e:Entity {memory_key: $memory_key, entity_id: row.entity_id})
                SET e.name = row.name, e.type = row.type
                WITH e, row
                WHERE row.grandchild_id IS NOT NULL
                MATCH (g:Knowledgechunk_grand {id: row.grandchild_id})
                MERGE (e)-[:PROVENANCE]->(g)
                """,
                params,
            )

        if relations:
            self._run_write(
                """
                UNWIND $relations AS row
                MATCH (s:Entity {memory_key: $memory_key, entity_id: row.source_id})
                MATCH (t:Entity {memory_key: $memory_key, entity_id: row.target_id})
                MERGE (s)-[r:RELATES_TO]->(t)
                SET r.type = row.type, r.weight = row.weight, r.memory_key = $memory_key
                """,
                params,
            )

        if claims:
            self._run_write(
                """
                UNWIND $claims AS row
                MERGE (c:Claim {memory_key: $memory_key, claim_id: row.claim_id})
                SET c.text = row.text, c.confidence = row.confidence
                WITH c, row
                OPTIONAL MATCH (e:Entity {memory_key: $memory_key, entity_id: row.entity_id})
                FOREACH (_ IN CASE WHEN e IS NULL THEN [] ELSE [1] END |
                  MERGE (c)-[:ABOUT]->(e)
                )
                WITH c, row
                WHERE row.grandchild_id IS NOT NULL
                MATCH (g:Knowledgechunk_grand {id: row.grandchild_id})
                MERGE (c)-[:PROVENANCE]->(g)
                """,
                params,
            )

        if communities:
            self._run_write(
                """
                UNWIND $communities AS row
                MERGE (c:Community {memory_key: $memory_key, community_id: row.community_id})
                SET c.level = row.level
                WITH c, row
                UNWIND row.entity_ids AS eid
                MATCH (e:Entity {memory_key: $memory_key, entity_id: eid})
                MERGE (e)-[:IN_COMMUNITY]->(c)
                """,
                params,
            )

        if summaries:
            self._run_write(
                """
                UNWIND $summaries AS row
                MERGE (s:CommunitySummary {memory_key: $memory_key, summary_id: row.summary_id})
                SET s.level = row.level, s.text = row.text
                WITH s, row
                MATCH (c:Community {memory_key: $memory_key, community_id: row.community_id})
                MERGE (c)-[:HAS_SUMMARY]->(s)
                """,
                params,
            )

        return {
            "memory_id": memory_id,
            "memory_key": memory_key,
            "version": version,
            "entities_created": len(entities),
            "relations_created": len(relations),
            "claims_created": len(claims),
            "communities_created": len(communities),
            "summaries_created": len(summaries),
        }

    def get_memory_bundle(self, memory_key: str) -> dict[str, Any] | None:
        rows = self._run_read(
            """
            MATCH (m:Memory {memory_key: $memory_key})
            OPTIONAL MATCH (m)-[:RETRIEVED]->(g:Knowledgechunk_grand)
            OPTIONAL MATCH (e:Entity {memory_key: $memory_key})
            OPTIONAL MATCH (c:Claim {memory_key: $memory_key})
            OPTIONAL MATCH (comm:Community {memory_key: $memory_key})
            RETURN m AS memory,
                   count(DISTINCT g) AS grandchild_count,
                   count(DISTINCT e) AS entity_count,
                   count(DISTINCT c) AS claim_count,
                   count(DISTINCT comm) AS community_count
            """,
            {"memory_key": memory_key},
        )
        if not rows:
            return None
        row = rows[0]
        memory = node_to_dict(row.get("memory"))
        return {
            "memory": memory,
            "grandchild_count": int(row.get("grandchild_count") or 0),
            "entity_count": int(row.get("entity_count") or 0),
            "claim_count": int(row.get("claim_count") or 0),
            "community_count": int(row.get("community_count") or 0),
        }

    def graph_search_local(
        self,
        *,
        seed_entity_id: str,
        hops: int = 2,
        memory_key: str | None = None,
    ) -> dict[str, Any]:
        hop_max = max(1, hops)
        key_clause = "AND start.memory_key = $memory_key" if memory_key else ""
        params: dict[str, Any] = {"seed_entity_id": seed_entity_id, "hop_max": hop_max}
        if memory_key:
            params["memory_key"] = memory_key

        rows = self._run_read(
            f"""
            MATCH (start:Entity {{entity_id: $seed_entity_id}})
            WHERE true {key_clause}
            OPTIONAL MATCH path = (start)-[:RELATES_TO*1..{hop_max}]-(other:Entity)
            WHERE ($memory_key IS NULL OR other.memory_key = $memory_key)
            WITH start, collect(DISTINCT other) AS others
            RETURN start AS seed, others AS entities
            """,
            params,
        )

        sources = self._provenance_sources_for_memory(memory_key, seed_entity_id=seed_entity_id)
        paths: list[dict[str, Any]] = []
        if rows:
            row = rows[0]
            entities = [node_to_dict(e) for e in (row.get("entities") or []) if e is not None]
            seed = node_to_dict(row.get("seed"))
            if seed:
                entities = [seed] + [e for e in entities if e.get("entity_id") != seed.get("entity_id")]
            paths.append({"entities": entities, "relations": [], "claims": []})

        return {"paths": paths, "community_summaries": [], "sources": sources}

    def graph_search_global(
        self,
        *,
        query: str,
        top_communities: int = 3,
        memory_key: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"q": query, "top_k": top_communities}
        key_clause = ""
        if memory_key:
            key_clause = "AND s.memory_key = $memory_key"
            params["memory_key"] = memory_key

        summary_rows = self._run_read(
            f"""
            CALL db.index.fulltext.queryNodes('community_summary_text', $q)
            YIELD node AS s, score
            WHERE node:CommunitySummary {key_clause}
            RETURN s AS summary, s.community_id AS community_id, s.level AS level,
                   s.text AS text, score
            ORDER BY score DESC
            LIMIT $top_k
            """,
            params,
        )

        summaries = [
            {
                "community_id": r.get("community_id"),
                "level": int(r.get("level") or 0),
                "text": r.get("text") or "",
            }
            for r in summary_rows
        ]

        paths: list[dict[str, Any]] = []
        if memory_key and summaries:
            entity_rows = self._run_read(
                """
                MATCH (e:Entity {memory_key: $memory_key})-[:IN_COMMUNITY]->(c:Community)
                WHERE c.community_id IN $community_ids
                RETURN c.community_id AS community_id, collect(e) AS entities
                """,
                {
                    "memory_key": memory_key,
                    "community_ids": [s["community_id"] for s in summaries],
                },
            )
            for row in entity_rows:
                entities = [node_to_dict(e) for e in (row.get("entities") or [])]
                paths.append(
                    {
                        "entities": entities,
                        "relations": [],
                        "claims": [],
                        "community_id": row.get("community_id"),
                    }
                )

        sources = self._provenance_sources_for_memory(memory_key)
        return {"paths": paths, "community_summaries": summaries, "sources": sources}

    def _provenance_sources_for_memory(
        self,
        memory_key: str | None,
        *,
        seed_entity_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if not memory_key and not seed_entity_id:
            return []
        if seed_entity_id:
            rows = self._run_read(
                """
                MATCH (e:Entity {entity_id: $seed_entity_id})-[:PROVENANCE]->(g:Knowledgechunk_grand)
                OPTIONAL MATCH (doc:Knowledge)-[:HAS_FAMILY]->(:Knowledgechunk_family)
                  -[:HAS_SECTION]->(:Knowledgechunk)-[:HAS_CHILD]->(:Knowledgechunk_sen)
                  -[:HAS_GRANDCHILD]->(g)
                RETURN g.id AS grandchild_id, doc.source_file AS source_file, 0.0 AS fusion_score
                LIMIT 20
                """,
                {"seed_entity_id": seed_entity_id},
            )
        else:
            rows = self._run_read(
                """
                MATCH (m:Memory {memory_key: $memory_key})-[:RETRIEVED]->(g:Knowledgechunk_grand)
                OPTIONAL MATCH (doc:Knowledge)-[:HAS_FAMILY]->(:Knowledgechunk_family)
                  -[:HAS_SECTION]->(:Knowledgechunk)-[:HAS_CHILD]->(:Knowledgechunk_sen)
                  -[:HAS_GRANDCHILD]->(g)
                RETURN g.id AS grandchild_id, doc.source_file AS source_file, 0.0 AS fusion_score
                """,
                {"memory_key": memory_key},
            )
        return [
            {
                "grandchild_id": r.get("grandchild_id"),
                "source_file": r.get("source_file"),
                "fusion_score": float(r.get("fusion_score") or 0.0),
            }
            for r in rows
        ]


_client: Neo4jClient | None = None


def get_neo4j_client() -> Neo4jClient:
    global _client
    if _client is None:
        _client = Neo4jClient()
    return _client


def close_neo4j_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
