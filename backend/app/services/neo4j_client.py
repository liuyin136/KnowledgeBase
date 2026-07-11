from __future__ import annotations

import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterable

from neo4j import Driver, GraphDatabase, ManagedTransaction, Session

from app.core.constants import CHILD_COARSE_INDEX_NAMES, COARSE_INDEX_NAMES, NEO4J_MAX_RETRIES
from app.core.exceptions import Neo4jError
from app.services.ingest_guard import assert_ingestible_source
from app.core.logging import get_logger
from app.models.neo4j_models import (
    Knowledge,
    KnowledgeChild,
    KnowledgeChunk,
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

    def delete_all_knowledge(self) -> dict[str, int]:
        """Delete every :Knowledge node and its :KnowledgeChunk children."""
        rows = self._run_write(
            """
            MATCH (k:Knowledge)
            OPTIONAL MATCH (k)-[:HAS_CHUNK]->(c:KnowledgeChunk)
            WITH collect(DISTINCT k) AS ks, collect(DISTINCT c) AS cs
            FOREACH (n IN cs | DETACH DELETE n)
            FOREACH (n IN ks | DETACH DELETE n)
            RETURN size(ks) AS knowledge_deleted, size(cs) AS chunks_deleted
            """,
            {},
        )
        if not rows:
            return {"knowledge_deleted": 0, "chunks_deleted": 0}
        return {
            "knowledge_deleted": int(rows[0]["knowledge_deleted"]),
            "chunks_deleted": int(rows[0]["chunks_deleted"]),
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
            OPTIONAL MATCH (k)-[:HAS_SECTION]->(p:Knowledgechunk)
            OPTIONAL MATCH (p)-[:HAS_CHILD]->(c:Knowledgechunk_sen)
            OPTIONAL MATCH (c)-[:HAS_GRANDCHILD]->(g:Knowledgechunk_grand)
            WITH collect(DISTINCT g) AS gs, collect(DISTINCT c) AS cs, collect(DISTINCT p) AS ps
            FOREACH (n IN gs | DETACH DELETE n)
            FOREACH (n IN cs | DETACH DELETE n)
            FOREACH (n IN ps | DETACH DELETE n)
            RETURN size(gs) AS grandchildren_deleted,
                   size(cs) AS children_deleted,
                   size(ps) AS parents_deleted
            """,
            {"source_file": source_file},
        )
        if not rows:
            return {"parents_deleted": 0, "children_deleted": 0, "grandchildren_deleted": 0}
        return {
            "parents_deleted": int(rows[0]["parents_deleted"]),
            "children_deleted": int(rows[0]["children_deleted"]),
            "grandchildren_deleted": int(rows[0]["grandchildren_deleted"]),
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
