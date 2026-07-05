# Backend Design Scope v1.1 – Local-First RAG Experimentation Platform

**Version**: 1.1 (Cleaned & Consolidated)  
**Date**: 2026-07-04  
**Status**: Ready for Implementation  
**Approved Scope Guardrail**: Standard paths only. Late Chunking and Agentic Chunking are explicitly deferred to post-v1. All content below reflects this constraint.

This document is the single source of truth for v1 backend implementation. It consolidates the original approved scope with detailed specifications for directory structure, Neo4j schema, error handling, and infrastructure.

---

## 1. v1 Scope Definition

### In Scope (Standard Paths Only)
- Long-Text Ingest Pipeline (standard sliding-window or direct)
- Child-Chunk Ingest Pipeline (Recursive, Semantic, Structure-Aware — no Late/Agentic)
- Query Embedding Pipeline (standard)
- Hybrid Search Pipeline (vector parent-level + child max-pooling + optional BM25 + optional reranker)
- Memory Store + Memory Cart
- Full metadata & observability on every run
- 6 thin vertical implementation slices

### Explicitly Out of Scope for v1
- Late Chunking
- Agentic Chunking / LLM-generated boundaries or context summaries
- Structured Chat (v2)
- GraphRAG or any agentic retrieval patterns
- Multi-user features or heavy authentication

### Success Criteria for v1
- Researcher can run controlled experiments comparing embedding approaches and retrieval parameters.
- Every experiment produces rich, queryable observability data.
- Hybrid Search baseline with parent-child awareness is tunable and observable.
- System runs reliably on GTX 3070 Ti class hardware with models ≤ 7B.

---

## 2. Core Principles

- **Simplicity first**: Standard paths only. No premature abstraction.
- **Observability is first-class**: Every pipeline step emits consistent, structured metadata.
- **Module boundaries are strict**: Chunking Module only finds boundaries. Embedding Module only produces vectors. Orchestrator owns coordination, timing, metadata, and transactions.
- **Parent-child hierarchy** is the foundation for meaningful retrieval experimentation.
- **Incremental & verifiable**: Work proceeds in thin vertical slices. Each slice leaves a working, testable system.

---

## 3. High-Level Architecture

**Core Modules**
- `PipelineOrchestrator` — thin coordination layer
- `ChunkingModule` — pure boundary detection
- `EmbeddingModule` — vectorization (standard paths)
- `RetrievalModule` — Hybrid Search logic
- `MetadataService` — standardized metadata creation
- `Neo4jClient` — thin wrapper for Cypher + vector operations

**Data Flow**
Document → Orchestrator → ChunkingModule → EmbeddingModule → Neo4j  
Query → Orchestrator → QueryEmbedding → RetrievalModule → Memory paths

---

## 4. Backend Project Directory Structure (v1)

```
backend/
├── app/
│   ├── main.py
│   ├── core/
│   │   ├── config.py
│   │   ├── logging.py
│   │   ├── exceptions.py
│   │   └── constants.py
│   ├── api/v1/                  # HTTP layer only
│   ├── schemas/                 # Pydantic request/response models
│   ├── services/                # Business logic
│   │   ├── orchestrator.py
│   │   ├── chunking.py
│   │   ├── embedding.py
│   │   ├── retrieval.py
│   │   └── metadata.py
│   ├── models/                  # Data classes / Neo4j representations
│   ├── db/
│   │   ├── neo4j_client.py
│   │   └── vector_index.py
│   ├── workers/                 # Background tasks (ingest/search)
│   └── utils/
├── tests/
├── docker/
├── scripts/                     # download_models.py, init_neo4j.py
├── pyproject.toml
└── requirements.txt
```

---

## 5. Neo4j Schema (v1)

**Nodes** (with key properties):
- `:Knowledge` (id, source_file, total_tokens, embedding_method, vector, experiment_id)
- `:KnowledgeChunk` (id, parent_doc_id, chunk_index, text, token_count, chunk_method, vector, experiment_id)
- `:UserQuery`, `:UserQueryChunk`, `:Memory`, `:MemoryCart`, `:Experiment`

**Relationships**:
- `(:Knowledge)-[:HAS_CHUNK]->(:KnowledgeChunk)`
- `(:UserQuery)-[:TRIGGERED]->(:Memory)-[:RETRIEVED]->(:KnowledgeChunk)`
- `(:MemoryCart)-[:CONTAINS]->(:Memory)`

**Indexes**: Vector indexes (HNSW, cosine) on Knowledge and KnowledgeChunk + full-text indexes for BM25.

Full creation scripts are defined in the accompanying `neo4j-schema-v1.md`.

---

## 6. Standardized Metadata Contract

Every run produces:
- `ChunkMetadata` (chunk_id, parent_doc_id, chunk_method, embedding_method, token_count, timings, experiment_id)
- `ExperimentRun` (experiment_id, description, embedding_approach, chunk_method, total_chunks, avg_tokens, total_time_ms, source_file)

All metadata is stored in Neo4j as node properties and exposed via API.

---

## 7. Pipeline Specifications (Standard Paths)

**7.1 Long-Text Ingest**  
Accept document → direct embedding or sliding window (≈30k window, 10% overlap) → store as `:Knowledge` + vector → emit metadata.

**7.2 Child-Chunk Ingest (Simplified)**  
```pseudocode
boundaries = ChunkingModule.DetermineBoundaries(text, config.chunk_method)
for each boundary:
    chunk_text = ...
    chunk_vector = EmbeddingModule.Embed(chunk_text)   # standard path
    metadata = MetadataService.CreateChunkMetadata(...)
    persist with parent-child relationship
```
Supported: Recursive, Semantic, Structure-Aware.

**7.3 Query Embedding**  
Create `:UserQuery` (long-text) + optional `:UserQueryChunk` → return vectors + metadata.

**7.4 Hybrid Search**  
1. Parent-level retrieval on `:Knowledge` (vector + optional BM25 + RRF)
2. Fetch child chunks
3. Child-level Max-Pooling
4. Optional reranker on top-N
5. Return scored results + full metadata

All parameters (`hybrid_alpha`, `use_bm25`, `use_reranker`, etc.) are explicit and logged.

**7.5 Memory Store & Memory Cart**  
Create `:Memory` links → researcher curates into `:MemoryCart` via selection.

---

## 8. Error Handling & Retry Strategy

- Custom exception hierarchy with consistent error response shape.
- Retry policy for embedding (max 3 attempts, exponential backoff).
- Retry for transient Neo4j errors.
- All errors logged with `experiment_id`, `stage`, and `error_code`.
- Failed jobs update `Experiment.status = "failed"` with error details.

---

## 9. Infrastructure & Environment (v1)

**Recommended Stack**:
- Base image: `nvidia/cuda:12.4.1-runtime-ubuntu22.04` + Python 3.12
- Services: `backend`, `api-worker` (for long tasks), `neo4j`, `redis`, `frontend`
- Model recommendations: BGE-M3 (primary), suitable small long-context Jina variants
- One-time setup: model download + Neo4j index initialization scripts

Full details in `infrastructure-environment-spec.md`.

---

## 10. Incremental Implementation Roadmap (6 Slices)

Each slice delivers working, testable functionality:

1. **Slice 1** — Experiment scaffolding + Long-Text Ingest + basic metadata
2. **Slice 2** — Child-Chunk ingest + parent-child linking
3. **Slice 3** — Query Embedding
4. **Slice 4** — Hybrid Search baseline (vector + child max-pooling)
5. **Slice 5** — Add BM25 + RRF + reranker toggle
6. **Slice 6** — Memory Store + Memory Cart

After each slice: tests pass, researcher can run real experiments with observability.

---

## 11. Extensibility Notes (Post-v1)

Late/Agentic paths can be added as new branches inside `ChunkingModule` / `EmbeddingModule` behind feature flags. The `PipelineOrchestrator` and metadata contract remain stable.

---

**End of Backend Design Scope v1.1**  
This document + the accompanying detailed specs (`neo4j-schema-v1.md`, `error-handling-retry-strategy.md`, `infrastructure-environment-spec.md`, `backend-directory-structure.md`) form the complete backend design foundation for v1.