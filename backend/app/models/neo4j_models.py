"""
models/neo4j_models.py — Pydantic v2 representations of Neo4j nodes + relationships.

Per neo4j-schema-v1.1.md §1 + §2. These are pure data carriers used by the
Neo4jClient (db/neo4j_client.py) for typed CRUD. The orchestrator constructs
these objects and passes them to the client; the client persists them via
parameterized Cypher.

NOTE: the task spec extends the canonical schema with `text` on :Knowledge
(parent long-text content for ChildChunk context retrieval) and additional
fields on :Memory (query_text, chunk_text, score, vector_score, bm25_score,
fused_score, reranker_score). No :Experiment node (removed); run metadata
is carried in-memory via ExperimentRunMetadata only.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class Knowledge(BaseModel):
    """(:Knowledge) — parent document node.

    For LongText ingest: one node per sliding window; embedding_method="LongText".
    For ChildChunk ingest: ONE parent node carrying the full-doc long-text
    embedding (embedding_method="LongText") — the context vector. Child chunks
    hang off it via (:Knowledge)-[:HAS_CHUNK]->(:KnowledgeChunk).
    For document UPLOAD (pre-ingest storage): embedding_method="Upload" with
    vector=None — the HNSW index skips null-vector nodes, so upload-time
    placeholders do not pollute search results. The orchestrator reads the
    text from these nodes during /ingest and creates real Knowledge nodes
    (with non-null vectors) for the actual embeddings.
    """

    id: str
    source_file: str
    total_tokens: int
    embedding_method: str  # "LongText" | "Upload"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    vector: Optional[List[float]] = None  # None for upload-time placeholders
    text: str  # v1.2 extension: parent long-text content (ChildChunk context)
    chunk_index: Optional[int] = None  # set when LongText path produces multiple windows
    char_start: Optional[int] = None
    char_end: Optional[int] = None


class KnowledgeChunk(BaseModel):
    """(:KnowledgeChunk) — child chunk node (parent-child hierarchy)."""

    id: str
    parent_doc_id: str
    chunk_index: int
    text: str
    token_count: int
    chunk_method: str  # "Recursive" | "Semantic" | "Structure-Aware"
    chunking_time_ms: float
    embedding_time_ms: float
    embedding_method: str  # "ChildChunk"
    vector: List[float]
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    section: Optional[str] = None


class UserQuery(BaseModel):
    """(:UserQuery) — embedded user query (LongText embedding)."""

    id: str
    text: str
    total_tokens: int
    embedding_method: str  # "LongText"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    vector: List[float]


class UserQueryChunk(BaseModel):
    """(:UserQueryChunk) — optional child chunks of a long user query."""

    id: str
    parent_query_id: str
    chunk_index: int
    text: str
    token_count: int
    chunk_method: str
    embedding_time_ms: float
    vector: List[float]


class Memory(BaseModel):
    """(:Memory) — a retrieval memory linking a query to a retrieved chunk.

    v1.2 extension: denormalize query/chunk text + per-stage scores onto the
    node so the memory browser can render without re-joining.
    """

    id: str
    user_query_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    success_score: Optional[float] = None
    notes: Optional[str] = None
    # v1.2 denormalized fields:
    query_text: str = ""
    chunk_id: Optional[str] = None
    chunk_text: Optional[str] = None
    score: Optional[float] = None  # final score
    vector_score: Optional[float] = None
    bm25_score: Optional[float] = None
    fused_score: Optional[float] = None
    reranker_score: Optional[float] = None


class MemoryCart(BaseModel):
    """(:MemoryCart) — researcher-curated collection of memories."""

    id: str
    name: str
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    researcher_id: Optional[str] = None  # future multi-user


# No :Experiment model (experiment node removed from Neo4j architecture)

class ContainsRel(BaseModel):
    """(:MemoryCart)-[:CONTAINS]->(:Memory) edge — used for cart membership."""

    cart_id: str
    memory_id: str
