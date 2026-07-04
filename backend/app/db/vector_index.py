"""
db/vector_index.py — Idempotent Neo4j schema initialization.

Runs ALL Cypher from neo4j-schema-v1.1.md §3 (constraints + vector indexes
1024-dim cosine + fulltext indexes) on startup and from `scripts/init_neo4j.py`.

Per the task spec, the v1.2 schema extends the canonical fulltext indexes:
  • knowledge_text — covers BOTH Knowledge.source_file AND Knowledge.text
  • knowledgechunk_text — covers KnowledgeChunk.text

All statements use `IF NOT EXISTS`, so this is safe to call repeatedly.
"""

from __future__ import annotations

from typing import List, Tuple

from neo4j import Driver

from app.core.constants import EMBEDDING_DIM
from app.core.logging import get_logger

logger = get_logger("rag.db.vector_index")

# ─── DDL statements (order matters: constraints first, then indexes) ─────────

CONSTRAINTS: List[str] = [
    "CREATE CONSTRAINT knowledge_id IF NOT EXISTS FOR (k:Knowledge) REQUIRE k.id IS UNIQUE",
    "CREATE CONSTRAINT knowledgechunk_id IF NOT EXISTS FOR (c:KnowledgeChunk) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT userquery_id IF NOT EXISTS FOR (q:UserQuery) REQUIRE q.id IS UNIQUE",
    "CREATE CONSTRAINT userquerychunk_id IF NOT EXISTS FOR (qc:UserQueryChunk) REQUIRE qc.id IS UNIQUE",
    "CREATE CONSTRAINT memory_id IF NOT EXISTS FOR (m:Memory) REQUIRE m.id IS UNIQUE",
    "CREATE CONSTRAINT memorycart_id IF NOT EXISTS FOR (c:MemoryCart) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT experiment_id IF NOT EXISTS FOR (e:Experiment) REQUIRE e.id IS UNIQUE",
]

# Vector indexes — HNSW, cosine, BGE-M3 1024 dims.
# NOTE: Neo4j 5.x supports `CREATE VECTOR INDEX ... OPTIONS {indexConfig: {...}}`.
VECTOR_INDEXES: List[str] = [
    f"""
    CREATE VECTOR INDEX knowledge_vector IF NOT EXISTS
    FOR (k:Knowledge) ON (k.vector)
    OPTIONS {{indexConfig: {{
      `vector.dimensions`: {EMBEDDING_DIM},
      `vector.similarity_function`: 'cosine'
    }}}}
    """.strip(),
    f"""
    CREATE VECTOR INDEX knowledgechunk_vector IF NOT EXISTS
    FOR (c:KnowledgeChunk) ON (c.vector)
    OPTIONS {{indexConfig: {{
      `vector.dimensions`: {EMBEDDING_DIM},
      `vector.similarity_function`: 'cosine'
    }}}}
    """.strip(),
    f"""
    CREATE VECTOR INDEX userquery_vector IF NOT EXISTS
    FOR (q:UserQuery) ON (q.vector)
    OPTIONS {{indexConfig: {{
      `vector.dimensions`: {EMBEDDING_DIM},
      `vector.similarity_function`: 'cosine'
    }}}}
    """.strip(),
]

# Full-text indexes for BM25. v1.2 extension: knowledge_text covers BOTH
# source_file AND text so BM25 can match against parent content too.
FULLTEXT_INDEXES: List[str] = [
    "CREATE FULLTEXT INDEX knowledge_text IF NOT EXISTS FOR (k:Knowledge) ON EACH [k.source_file, k.text]",
    "CREATE FULLTEXT INDEX knowledgechunk_text IF NOT EXISTS FOR (c:KnowledgeChunk) ON EACH [c.text]",
    "CREATE FULLTEXT INDEX userquery_text IF NOT EXISTS FOR (q:UserQuery) ON EACH [q.text]",
]


def ensure_vector_indexes(driver: Driver, database: str = "neo4j") -> List[Tuple[str, str]]:
    """Create all constraints + vector + fulltext indexes (idempotent).

    Returns a list of (statement_kind, status) tuples for logging.
    """
    results: List[Tuple[str, str]] = []
    all_statements: List[Tuple[str, str]] = (
        [("constraint", c) for c in CONSTRAINTS]
        + [("vector_index", v) for v in VECTOR_INDEXES]
        + [("fulltext_index", f) for f in FULLTEXT_INDEXES]
    )

    with driver.session(database=database) as session:
        for kind, stmt in all_statements:
            # Truncate for log readability
            preview = " ".join(stmt.split())
            try:
                session.run(stmt).consume()
                results.append((kind, "ok"))
                logger.info(
                    "neo4j.schema.apply",
                    extra={"event": "neo4j.schema.apply", "kind": kind, "stmt": preview[:160]},
                )
            except Exception as exc:
                # Idempotent statements shouldn't fail — but if a version mismatch
                # (e.g. vector index unsupported) we log + continue.
                results.append((kind, f"error: {exc}"))
                logger.warning(
                    "neo4j.schema.apply_failed",
                    extra={
                        "event": "neo4j.schema.apply_failed",
                        "kind": kind,
                        "stmt": preview[:160],
                        "error": str(exc),
                    },
                )
    return results


# Public list for scripts/init_neo4j.py to iterate + print.
ALL_STATEMENTS: List[Tuple[str, str]] = (
    [("constraint", c) for c in CONSTRAINTS]
    + [("vector_index", v) for v in VECTOR_INDEXES]
    + [("fulltext_index", f) for f in FULLTEXT_INDEXES]
)
