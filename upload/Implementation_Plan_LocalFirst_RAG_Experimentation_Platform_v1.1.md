# Implementation Plan: Local-First RAG Experimentation Platform v1.1

**Version**: 1.0  
**Date**: 2026-07-04  
**Status**: Ready for Execution (Contract-First, 6-Slice Vertical Roadmap)  
**Aligned With**:
- [Backend_Design_Scope_v1.1.md](./Backend_Design_Scope_v1.1.md) (single source of truth for scope, architecture, pipelines, success criteria)
- [API_Interface_Design_v1.1.md](./API_Interface_Design_v1.1.md) (stable REST contract, types, error semantics)
- [backend-directory-structure_v1.1.md](./backend-directory-structure_v1.1.md) (project layout)
- [Frontend_Workflow_Mapping_v1.1.md](./Frontend_Workflow_Mapping_v1.1.md) (workflows + component mapping)
- [infrastructure-environment-spec_v1.1.md](./infrastructure-environment-spec_v1.1.md) (Docker, models, GTX 3070 Ti constraints)
- [neo4j-schema-v1.1.md](./neo4j-schema-v1.1.md) (nodes, relationships, indexes)
- [error-handling-retry-strategy_v1.1.md](./error-handling-retry-strategy_v1.1.md) (exception hierarchy + retry)

---

## Overview

Build a **local-first RAG experimentation platform** that lets a researcher systematically compare embedding approaches (`LongText` vs `ChildChunk`) and chunking methods (`Recursive` | `Semantic` | `Structure-Aware`) with full parent-child awareness, hybrid retrieval (vector + optional BM25 + reranker), rich observability, and curation via Memory + MemoryCart.

The implementation strictly follows the **6 thin vertical slices** defined in Backend_Design_Scope_v1.1.md so that after Slice 1 a researcher can already run real, observable Long-Text experiments. Every pipeline step emits `ChunkMetadata` and `ExperimentRun` for learnability. The system targets **GTX 3070 Ti (8 GB VRAM)** with models ≤ 7 B parameters (primary: BGE-M3).

**Core workflows supported end-to-end**:
1. Ingest (document upload + configurable chunk/embed + live progress + metadata)
2. Hybrid Search (tunable parent-level retrieval + child expansion + Memory Cart add)
3. Memory Cart (curation)
4. Experiments (history, detail, side-by-side comparison, observability browser)

**Non-goals for v1** (explicit guardrails): Late Chunking, Agentic Chunking, GraphRAG, Structured Chat, multi-user auth.

**Success criteria** (from Backend_Design_Scope):
- Researcher can run controlled experiments comparing approaches/parameters.
- Every run produces rich, queryable observability data in Neo4j.
- Hybrid Search baseline with parent-child awareness is tunable and observable.
- System runs reliably on target hardware.

This plan decomposes the work into **ordered, verifiable S/M tasks** with explicit acceptance criteria, verification steps, dependencies, and files touched. It follows vertical slicing so each increment leaves a **working, testable system**.

---

## Architecture Decisions & Key Principles (Via Negativa + Tinkering)

**Decisions** (drawn directly from the design docs):
- **Vertical slices win**: One complete feature path at a time (e.g. "researcher can run a Long-Text ingest experiment with full metadata" before adding ChildChunk). Avoid horizontal layering (all DB then all API then all UI).
- **Strict module boundaries** (non-negotiable):
  - `ChunkingModule` → only finds boundaries (never embeds).
  - `EmbeddingModule` → only produces vectors (never chunks).
  - `PipelineOrchestrator` → owns coordination, timing, metadata emission, transactions, experiment lifecycle.
- **Parent-child hierarchy is the foundation** for all meaningful retrieval experiments (`:Knowledge` → `[:HAS_CHUNK]` → `:KnowledgeChunk`).
- **Observability is first-class**: `ChunkMetadata` (per-chunk tokens, timings, method, experiment_id) and `ExperimentRun` are emitted at every step and persisted/queryable.
- **Contract-first API**: Pydantic schemas in `schemas/` are the single source of truth. `api/` layer is thin HTTP only. Error shape is always `{"error": {"code", "message", "details"}}`.
- **Standard paths only in v1**: No Late/Agentic logic. All extensibility prepared via clean module structure + feature flags (post-v1).
- **Local-first infrastructure**: Docker + NVIDIA CUDA base + Neo4j 5.x (vector HNSW + fulltext) + Redis (jobs/progress) + separate `api-worker`. One-time model download + index init scripts.
- **Frontend architecture**: Next.js 15 App Router + TypeScript + shadcn/ui (neutral + teal) + TanStack Query v5 (server state) + Zustand (client state) + react-hook-form + zod. Long-running progress via SSE or polling.
- **Tinkering enabled by design** (Antifragility): Every tunable parameter (`hybridAlpha`, `chunkMethod`, `embeddingApproach`, `useBm25`, `useReranker`, `topKVector`, `topNRerank`, `parentContextLevels`) is explicit in request bodies, logged per run, and visible on Experiments page. Researcher can rapidly iterate and compare.
- **Via Negativa (what we deliberately avoid)**: No premature abstraction, no over-engineering for v2 features, no leaking internal stack traces, no retry on permanent failures (validation, model load), no storing large files in Neo4j (only metadata + vectors).

**Dependency graph (bottom-up order)**:
```
Neo4j schema + indexes + models
    ↓
Core services (chunking/embedding/metadata/orchestrator) + error handling
    ↓
API schemas + thin endpoints + workers (job status)
    ↓
Frontend types/clients + workflow pages (Ingest first, then Search/Memory/Experiments)
    ↓
Integration tests + contract tests + observability polish
```

---

## Task List (Granular, Verifiable, Vertical)

All tasks are sized so one focused session can complete + verify them. Checkpoints after every major phase.

### Phase 0: Infrastructure, Scaffolding & Contracts (Foundation — can start immediately)

**Task 0.1: Backend project scaffolding + core configuration + exception hierarchy**

**Description:** Create exact directory tree per `backend-directory-structure_v1.1.md`. Implement `core/config.py` (Pydantic Settings for NEO4J_*, REDIS_URL, MODEL_PATH, CUDA_VISIBLE_DEVICES), `core/exceptions.py` (RAGBaseException + subclasses per error-handling spec), `core/logging.py` (structured JSON logs with experiment_id/correlation_id), constants/enums for ChunkMethod/EmbeddingApproach. Add basic `main.py` with FastAPI lifespan that initializes Neo4j driver + Redis.

**Acceptance criteria:**
- [ ] Directory tree exactly matches spec (app/api/v1/, services/, db/, workers/, schemas/, models/, utils/)
- [ ] `from app.core.config import settings` loads env vars correctly; validation errors raised on missing required vars
- [ ] Custom exceptions inherit correctly; `status_code` and `code` attributes present
- [ ] `uvicorn app.main:app` starts and `/health` (or root) returns 200 without DB connection yet

**Verification:**
- [ ] `python -c "from app.main import app; print('imports OK')"`
- [ ] Pytest collection succeeds on `tests/`
- [ ] `.env.example` documents all variables from infrastructure spec

**Dependencies:** None  
**Files likely touched:** ~6 files (pyproject.toml, requirements.txt or uv.lock, app/main.py, app/core/*.py, .env.example, README.md)  
**Estimated scope:** Medium (Scaffold + config)

**Task 0.2: Docker multi-stage build + docker-compose.yml + one-time scripts (models + Neo4j init)**

**Description:** Implement `docker/Dockerfile` (multi-stage: model-downloader stage with huggingface_hub + git-lfs, runtime stage based on `nvidia/cuda:13.3.0-devel-ubuntu26.04` or approved base + Python 3.12/3.13, minimal deps). Create `docker-compose.yml` with services: neo4j (5.20-community + APOC if needed), redis:7-alpine, backend (GPU reserved), api-worker (GPU reserved, runs RQ worker or equivalent), frontend. Implement stub `scripts/download_models.py` (downloads BGE-M3 + optional small reranker to MODEL_PATH) and `scripts/init_neo4j.py` (runs Cypher for constraints + vector indexes + fulltext indexes).

**Acceptance criteria:**
- [ ] `docker compose build --no-cache` succeeds for all services
- [ ] `docker compose run --rm backend python scripts/download_models.py` downloads BGE-M3 without error and places in /app/models
- [ ] `docker compose run --rm backend python scripts/init_neo4j.py` creates all constraints and indexes listed in neo4j-schema-v1.1.md (vector 1024-dim cosine on Knowledge & KnowledgeChunk, fulltext on text fields)
- [ ] GPU visible: `docker compose run --rm backend nvidia-smi` shows the card

**Verification:**
- [ ] `docker compose ps` shows healthy services after `up -d`
- [ ] Neo4j Browser or `cypher-shell` confirms indexes exist
- [ ] No OOM or permission errors on model download

**Dependencies:** None (parallel with 0.1)  
**Files:** Dockerfile, docker-compose.yml, scripts/*.py, .dockerignore  
**Estimated scope:** Medium

**Task 0.3: Neo4j client wrapper + vector index helper + basic CRUD for core nodes**

**Description:** Implement thin `db/neo4j_client.py` (driver singleton, context-managed sessions/transactions, retry on transient errors). Implement `db/vector_index.py` helpers. Add methods to create/get :Experiment, :Knowledge, :KnowledgeChunk nodes and relationships per neo4j-schema. Use parameterized Cypher. Add basic timing utils.

**Acceptance criteria:**
- [ ] `Neo4jClient` can create Experiment node and return its id
- [ ] Can create Knowledge node with vector property (list[float]) and HAS_CHUNK relationship to a KnowledgeChunk
- [ ] Vector index creation is idempotent (IF NOT EXISTS)
- [ ] All writes use transactions; transient Neo4j errors trigger retry (max 2)

**Verification:**
- [ ] Unit tests in `tests/unit/test_neo4j_client.py` pass (mock driver or integration with test container)
- [ ] Manual: create experiment → verify in Neo4j Browser

**Dependencies:** Task 0.1, Task 0.2 (running Neo4j)  
**Files:** app/db/neo4j_client.py, app/db/vector_index.py, app/utils/timing.py, tests/unit/test_neo4j_client.py  
**Estimated scope:** Small-Medium

**Task 0.4: Frontend Next.js 15 + shadcn/ui + state management scaffolding + navigation**

**Description:** Initialize `frontend/` with Next.js 15 (App Router, TypeScript, Tailwind, ESLint). Install and configure shadcn/ui (neutral theme + teal accent, dark mode). Set up TanStack Query v5 provider, Zustand store skeleton, react-hook-form + zod. Create root layout with sidebar navigation (Dashboard, Ingest, Hybrid Search, Memory Cart, Experiments) matching Frontend_Workflow_Mapping_v1.1.md. Add stub pages for each route. Add OpenAPI client generation or manual TypeScript types matching API_Interface_Design (or use `openapi-typescript` later).

**Acceptance criteria:**
- [ ] `npm run dev` starts on port 3000; no console errors
- [ ] Sidebar renders all 5 nav links; clicking navigates (even if page is placeholder)
- [ ] Dark mode + teal accent visible; responsive on mobile
- [ ] TanStack Query devtools available in dev mode; basic query example works

**Verification:**
- [ ] `npm run build` succeeds with no type errors
- [ ] Lighthouse or manual: core web vitals baseline recorded (for later optimization)

**Dependencies:** None (parallel)  
**Files:** Many in frontend/ (package.json, next.config.ts, app/layout.tsx, app/globals.css, components/ui/*, app/(pages)/*, lib/api-client.ts or generated)  
**Estimated scope:** Medium (scaffolding + design system)

### Checkpoint 0: Foundation Ready (After Phase 0)

- [ ] Full stack boots cleanly via `docker compose up -d`
- [ ] Models present, Neo4j constraints + vector/fulltext indexes created
- [ ] Backend imports + basic health OK; frontend dev server responsive with navigation
- [ ] Researcher can run `docker compose run --rm backend python scripts/init_neo4j.py` again safely (idempotent)
- [ ] Plan reviewed; go/no-go for Phase 1

---

### Phase 1: Slice 1 — Experiment Scaffolding + Long-Text Ingest + Basic Metadata (First Vertical Slice — Researcher Can Already Experiment)

**Task 1.1: Pydantic schemas for Experiment, IngestConfig, Document + Experiment API endpoints (contract-first)**

**Description:** Create `schemas/experiment.py`, `schemas/ingest.py`, `schemas/document.py`, `schemas/common.py` (Pagination, ErrorResponse) exactly matching types and error contract in API_Interface_Design_v1.1.md and Backend_Design_Scope. Implement thin `api/v1/experiments.py` and `api/v1/documents.py` routers (POST/GET/DELETE with pagination). Wire into `api/v1/router.py`. Add dependency for experiment context if needed. Use Pydantic v2 strict mode.

**Acceptance criteria:**
- [ ] POST /api/v1/experiments accepts valid IngestConfig payload and returns 201 {id, status, created_at, ...}
- [ ] GET /api/v1/experiments returns paginated list with correct shape
- [ ] All non-2xx responses use exact `{"error": {"code", "message", "details"}}` shape
- [ ] OpenAPI schema at /docs reflects the contract (no drift)

**Verification:**
- [ ] `pytest tests/contract/test_api_contract.py` or similar passes (validate against expected OpenAPI)
- [ ] Manual curl POST → GET cycle works; Neo4j has :Experiment node
- [ ] FastAPI validation errors return 422 with proper error code

**Dependencies:** Task 0.1 (core + exceptions)  
**Files:** app/schemas/*.py (4-5 files), app/api/v1/experiments.py, app/api/v1/documents.py, app/api/v1/router.py, app/main.py (include router)  
**Estimated scope:** Small-Medium (contract is already defined)

**Task 1.2: EmbeddingModule (standard LongText path) + model loading singleton**

**Description:** Implement `services/embedding.py`: `EmbeddingModule` class with `embed_text(text: str) -> list[float]` using BGE-M3 (via sentence-transformers or transformers + optimum). Handle model loading once (lifespan or module-level with lock). Support batching for future but keep simple for v1. Add timing around embedding call. Integrate with error handling (EmbeddingError on failure, retry via tenacity only on transient).

**Acceptance criteria:**
- [ ] `embed_text("hello world")` returns 1024-dim vector (BGE-M3)
- [ ] Model loads into GPU memory on first call; subsequent calls reuse
- [ ] Embedding time is measured and returned in metadata later
- [ ] CUDA OOM or load failure raises EmbeddingError (not swallowed)

**Verification:**
- [ ] Unit test mocks model or uses small test model; real GPU test in integration
- [ ] VRAM usage after load < ~4-5 GB for BGE-M3 (comfortable headroom)

**Dependencies:** Task 0.2 (models downloaded), Task 0.1 (config)  
**Files:** app/services/embedding.py, app/core/lifespan.py or main.py (model preload optional), tests/unit/test_embedding.py  
**Estimated scope:** Small (focused module)

**Task 1.3: ChunkingModule for Long-Text path (direct or simple sliding-window)**

**Description:** Implement `services/chunking.py`: `ChunkingModule` with `determine_boundaries(text, method) -> list[dict]` or direct long-text splitter. For LongText path in v1: either treat whole document as one "chunk" (stored as :Knowledge) or apply simple sliding window (~25-30k tokens, 10% overlap) using tokenizer. Do **not** implement Recursive/Semantic/Structure-Aware yet (those come in Slice 2). Emit basic chunk metadata skeleton.

**Acceptance criteria:**
- [ ] For a 10k token document, LongText path produces 1 or few parent-level chunks
- [ ] Token count calculated correctly (use model tokenizer or tiktoken)
- [ ] Overlap logic works if sliding window chosen; boundaries respect sentence/paragraph where possible
- [ ] Method="LongText" or equivalent recorded

**Verification:**
- [ ] Unit tests with sample texts of varying length
- [ ] Token counts match expected for BGE-M3 tokenizer

**Dependencies:** Task 0.1, Task 1.2 (tokenizer access)  
**Files:** app/services/chunking.py, app/utils/tokenization.py, tests/unit/test_chunking.py  
**Estimated scope:** Small

**Task 1.4: MetadataService + basic ExperimentRun / ChunkMetadata emission**

**Description:** Implement `services/metadata.py`: factory functions `create_chunk_metadata(...) -> ChunkMetadata`, `create_experiment_run(...) -> ExperimentRun` (or dicts matching the interfaces in design docs). These are pure and called by orchestrator. Persist as node properties or separate nodes as per neo4j-schema.

**Acceptance criteria:**
- [ ] Metadata dicts contain all required fields (chunk_id, parent_doc_id, chunk_method, embedding_method, token_count, timings, experiment_id, etc.)
- [ ] Can be serialized to JSON for API responses without loss

**Verification:**
- [ ] Unit tests assert presence of all fields and correct types
- [ ] Sample metadata appears in Neo4j node properties after ingest

**Dependencies:** Task 0.3 (neo4j models)  
**Files:** app/services/metadata.py, app/models/neo4j_models.py (pydantic or dataclass versions), tests/unit/test_metadata.py  
**Estimated scope:** Small

**Task 1.5: PipelineOrchestrator for Long-Text Ingest flow + job status tracking**

**Description:** Implement `services/orchestrator.py`: `ingest_long_text(document, config, experiment_id)` that coordinates ChunkingModule → EmbeddingModule → MetadataService → Neo4j persist (Knowledge + optional windows as chunks) → update Experiment status. Make the whole flow idempotent where possible. Integrate with workers (RQ/Celery/FastAPI BackgroundTasks + Redis) so API returns 202 immediately. Implement `get_ingest_status(job_id)` that polls Redis or DB for progress + last error.

**Acceptance criteria:**
- [ ] POST /ingest (or unified) with LongText config triggers background job; API returns 202 {jobId, experimentId, status}
- [ ] On success: :Knowledge node + vector exists, Experiment.status = "completed", total_time_ms recorded
- [ ] On transient embedding failure: tenacity retries (max 3, exp backoff); permanent failure marks status="failed" + error details
- [ ] GET /ingest/{jobId}/status returns current state (running/completed/failed) + any ChunkMetadata emitted so far

**Verification:**
- [ ] End-to-end integration test (tests/integration/test_ingest_flow.py): upload small .txt, poll until completed, assert Neo4j state + metadata
- [ ] Failed job (e.g. bad model path) surfaces error via status endpoint and Experiment node

**Dependencies:** Tasks 1.1–1.4, Task 0.3 (neo4j writes), workers setup  
**Files:** app/services/orchestrator.py, app/workers/tasks.py, app/workers/progress.py, app/api/v1/ingest.py, app/db/neo4j_client.py (add persist methods)  
**Estimated scope:** Medium-Large (core orchestration — split further if session >2h)

**Task 1.6: Wire ingest + document upload endpoints + basic error propagation**

**Description:** Complete `api/v1/ingest.py` and `api/v1/documents.py` (multipart upload handling, store file temporarily or stream, trigger orchestrator). Ensure all errors from services bubble up through global exception handler to the standard error shape. Add correlation_id propagation.

**Acceptance criteria:**
- [ ] Multipart POST /documents or direct to /ingest accepts PDF/TXT/MD and triggers LongText ingest
- [ ] 4xx/5xx errors always return the contract error JSON (never HTML or stack trace)
- [ ] experiment_id and job_id flow through logs and responses

**Verification:**
- [ ] Contract test + manual error injection (bad file, OOM simulation) produces correct codes (VALIDATION_ERROR, INGEST_FAILED, etc.)
- [ ] Structured logs contain experiment_id on error paths

**Dependencies:** Task 1.5, Task 0.1 (exceptions + logging)  
**Files:** app/api/v1/ingest.py, app/api/v1/documents.py, app/core/exceptions.py (global handler in main.py), tests/contract/  
**Estimated scope:** Small

**Task 1.7: Basic unit + integration tests for Slice 1 + observability check**

**Description:** Add tests for chunking, embedding, metadata, orchestrator happy path + error paths. Add one integration test that exercises full Long-Text ingest and verifies Experiment + Knowledge nodes + metadata queryable via future GET /experiments/{id}/chunks.

**Acceptance criteria:**
- [ ] All new unit tests pass (`pytest tests/unit/ -k "chunking or embedding or metadata or orchestrator"`)
- [ ] Integration test passes end-to-end on GPU-enabled runner
- [ ] Researcher can query Neo4j for ChunkMetadata-like properties after a run

**Verification:**
- [ ] CI-like: `pytest --cov=app/services --cov=app/api` reports >70% on new code (or explicit list of covered paths)
- [ ] Manual: run ingest via curl or simple frontend stub → see experiment in list

**Dependencies:** All previous in Phase 1  
**Files:** tests/unit/test_*.py (new), tests/integration/test_ingest_flow.py, pyproject.toml (pytest config)  
**Estimated scope:** Small-Medium

### Checkpoint 1: Slice 1 Complete — First Working Experiment Loop

- [ ] Researcher can: create experiment → upload document → configure LongText ingest → poll status → view completed experiment with metadata/timings in Neo4j or via API
- [ ] All tests pass; build clean
- [ ] Observability data (tokens, embedding time, total_time_ms) visible and correct
- [ ] Ready for researcher tinkering with LongText path (different docs, monitor VRAM)

**Parallelization note**: While Phase 1 executes, frontend types can be generated from OpenAPI spec (once Task 1.1 done) and basic Ingest page UI can be built in parallel by another agent/session (form for config + file upload + progress polling + results table).

---

### Phase 2: Slice 2 + 3 — Child-Chunk Ingest + Parent-Child Linking + Query Embedding

**Task 2.1: Extend ChunkingModule with Recursive, Semantic, Structure-Aware strategies (standard paths only)**

**Description:** Add implementations inside `ChunkingModule` for the three supported methods (use langchain text_splitters or equivalent simple recursive/semantic logic; Structure-Aware can be markdown/header-aware or basic). Keep logic pure (no embedding). Update determine_boundaries signature to accept config.chunk_method. For Semantic, keep simple (no heavy LLM calls in v1).

**Acceptance criteria:**
- [ ] Recursive produces overlapping chunks of target size
- [ ] Semantic produces chunks based on sentence similarity or basic clustering (acceptable simple version)
- [ ] Structure-Aware respects headings/sections if input is markdown
- [ ] All methods record chunk_method and chunk_index correctly

**Verification:**
- [ ] Unit tests with sample markdown/text assert correct number of chunks and boundaries
- [ ] No embedding calls inside chunking module (pure boundary detection)

**Dependencies:** Task 1.3  
**Files:** app/services/chunking.py (extend), tests/unit/test_chunking.py (add cases)  
**Estimated scope:** Medium

**Task 2.2: Extend orchestrator + metadata for ChildChunk path + parent-child persistence**

**Description:** Add `ingest_child_chunk(...)` flow in orchestrator. For each boundary: create chunk_text → embed (via EmbeddingModule) → create ChunkMetadata → persist :KnowledgeChunk + vector + HAS_CHUNK relationship from parent :Knowledge. Support both LongText parent + child chunks in same experiment if configured. Update Experiment.total_chunks, avg_tokens_per_chunk etc.

**Acceptance criteria:**
- [ ] Ingest with embeddingApproach="ChildChunk" + any chunkMethod produces multiple :KnowledgeChunk nodes linked to one :Knowledge
- [ ] Parent vector (if LongText also stored) and child vectors coexist correctly
- [ ] Metadata includes parent_doc_id, chunk_index, token_count, timings per chunk

**Verification:**
- [ ] Integration test: ChildChunk ingest → query Neo4j for HAS_CHUNK relationships and count
- [ ] ExperimentRun metadata reflects total_chunks > 1 and correct avg

**Dependencies:** Tasks 1.4, 1.5, 2.1  
**Files:** app/services/orchestrator.py (new method), app/services/metadata.py (extend), app/db/neo4j_client.py (persist_chunk + link)  
**Estimated scope:** Medium

**Task 2.3: Query Embedding pipeline (UserQuery + optional UserQueryChunk)**

**Description:** Implement query embedding path (for later search). Create :UserQuery node (long-text vector) and optional :UserQueryChunk if query is long. Reuse EmbeddingModule. Add to orchestrator or new query service.

**Acceptance criteria:**
- [ ] Embedding a raw query produces :UserQuery node with vector and metadata
- [ ] Long query can be optionally chunked (reuse chunking logic) → :UserQueryChunk nodes

**Verification:**
- [ ] Unit/integration test creates UserQuery and retrieves its vector

**Dependencies:** Task 1.2 (embedding), Task 2.1 (chunking reuse)  
**Files:** app/services/orchestrator.py or new query_embedding.py, app/db/neo4j_client.py (persist_user_query)  
**Estimated scope:** Small

### Checkpoint 2: ChildChunk + Query Embedding Working

- [ ] Researcher can run ChildChunk experiments (different chunk methods) and see parent-child graph in Neo4j
- [ ] Query embedding path ready for retrieval slice
- [ ] All previous Slice 1 functionality still works (regression free)

---

### Phase 3: Slice 4 + 5 — Hybrid Search Baseline + BM25 + Reranker Toggle

**Task 3.1: RetrievalModule — parent-level vector search + child max-pooling + result assembly**

**Description:** Implement `services/retrieval.py`: `hybrid_search(raw_query, config: SearchConfig, experiment_id?)`. Step 1: embed query. Step 2: parent-level vector search on :Knowledge (cosine, topK). Step 3: for each parent fetch top child chunks via max-pooling or score propagation. Step 4: optional RRF fusion if BM25 later. Return scored SearchResult list with full metadata (parent context, chunk text, scores, config used).

**Acceptance criteria:**
- [ ] Vector-only search returns relevant parents + their child chunks with scores
- [ ] Child max-pooling logic implemented and documented
- [ ] SearchResult shape matches API spec; includes experiment_id linkage if provided
- [ ] All retrieval parameters logged in metadata

**Verification:**
- [ ] Integration test with known documents: query returns expected chunks with high similarity
- [ ] Manual: different hybridAlpha values change result ordering as expected

**Dependencies:** Phase 2 (child chunks exist), Task 2.3 (query embed)  
**Files:** app/services/retrieval.py, app/db/neo4j_client.py (vector_search_parents, get_child_chunks, etc.), tests/unit/test_retrieval.py  
**Estimated scope:** Medium-Large (core retrieval logic)

**Task 3.2: Add BM25 + RRF + optional reranker toggle (Slice 5)**

**Description:** Extend RetrievalModule. Add fulltext BM25 search on :Knowledge / :KnowledgeChunk (using Neo4j fulltext indexes). Implement RRF (Reciprocal Rank Fusion) to combine vector + BM25 scores when useBm25=true. Add optional small cross-encoder reranker (BGE-reranker or Jina) on top-N results when useReranker=true. All toggles explicit in SearchConfig and logged.

**Acceptance criteria:**
- [ ] useBm25=true changes results vs pure vector (measurable difference)
- [ ] RRF fusion implemented correctly (higher combined score for docs good in both)
- [ ] useReranker=true re-scores top results and improves precision on test set (qualitative OK for v1)
- [ ] Search still fast on target hardware

**Verification:**
- [ ] Side-by-side comparison test (same query, different config flags) shows expected behavior
- [ ] Performance: p95 search < few seconds even with reranker on modest corpus

**Dependencies:** Task 3.1, Neo4j fulltext indexes (already in Phase 0)  
**Files:** app/services/retrieval.py (extend), app/db/neo4j_client.py (fulltext search methods)  
**Estimated scope:** Medium

**Task 3.3: Search API endpoints + history + metadata exposure**

**Description:** Implement `api/v1/search.py`: POST /search (rawQuery + config + optional experimentId) → returns {searchId, results, metadata}. GET /searches/history (paginated). Ensure SearchConfig validation and full logging of parameters used.

**Acceptance criteria:**
- [ ] POST /search returns results with parent context, scores, chunk metadata
- [ ] History endpoint lists past searches with config snapshot
- [ ] experimentId filter works (only search within that experiment's data)

**Verification:**
- [ ] Contract test + manual search returns expected shape
- [ ] Changing hybridAlpha / useReranker visibly affects results and is recorded

**Dependencies:** Task 3.1/3.2, Task 1.1 (schemas)  
**Files:** app/api/v1/search.py, app/schemas/search.py, app/services/orchestrator.py (search orchestration)  
**Estimated scope:** Small-Medium

### Checkpoint 3: Tunable Hybrid Search Working End-to-End

- [ ] Researcher can run searches with different configs (alpha, BM25 on/off, reranker on/off) and see impact immediately
- [ ] Results include rich metadata for analysis
- [ ] Search history persisted and re-runnable

---

### Phase 4: Slice 6 — Memory Store + Memory Cart + Full Frontend Workflows

**Task 4.1: Memory + MemoryCart domain + API (create, list, patch selection)**

**Description:** Implement Memory and MemoryCart schemas, services, and api/v1/memory.py endpoints (POST /memories, POST /memory-carts, GET /memory-carts, PATCH /memory-carts/{id} for selection updates). Persist :Memory nodes linked from UserQuery → RETRIEVED → KnowledgeChunk. :MemoryCart CONTAINS Memories. Add basic curation logic.

**Acceptance criteria:**
- [ ] From search results, user can "add to memory cart" → creates Memory + links
- [ ] MemoryCart can be created, listed, and updated with selected memories
- [ ] Relationships correct in Neo4j

**Verification:**
- [ ] Full flow: search → add to cart → view cart shows selected chunks with context

**Dependencies:** Phase 3 (search results exist)  
**Files:** app/schemas/memory.py, app/api/v1/memory.py, app/services/memory.py or orchestrator extension, app/db/neo4j_client.py  
**Estimated scope:** Medium

**Task 4.2: Complete frontend pages for all 4 workflows + Experiments observability (Ingest, Hybrid Search, Memory Cart, Experiments)**

**Description:** Build production-quality pages per Frontend_Workflow_Mapping_v1.1.md using shadcn components:
- Ingest: config form (embeddingApproach, chunkMethod), file upload, live progress (polling or SSE), per-chunk metadata table, chunk inspector drawer, link to experiment on done.
- Hybrid Search: query input + SearchConfig controls (sliders, toggles for BM25/reranker, topK), results list with scores/badges/parent context, multi-select + "Add to Memory Cart", past searches history.
- Memory Cart: list of carts, detail with checkbox selection table, save/edit.
- Experiments: table (id, date, description, embedding_approach, chunk_method, #chunks, total_time), click → detail with full stats + chunk browser + observability panel, basic side-by-side comparison of two experiments.
Use TanStack Query for all data fetching, optimistic updates where helpful, Zod validation on forms.

**Acceptance criteria:**
- [ ] All pages load without errors; dark mode + teal theme consistent
- [ ] Ingest flow works end-to-end (upload → progress updates → experiment created with metadata visible)
- [ ] Search config changes affect results; "Add to Memory Cart" persists
- [ ] Experiments table sortable/filterable; detail shows ChunkMetadata table + timings; comparison mode works for 2 experiments
- [ ] Accessible (basic a11y: labels, keyboard nav, contrast)

**Verification:**
- [ ] Manual user journey test for each workflow
- [ ] `npm run build` clean; no TypeScript errors
- [ ] TanStack Query cache invalidation works after mutations (new experiment appears in list)

**Dependencies:** Phase 0.4 (scaffolding), Phase 1-3 (working APIs), Task 4.1  
**Files:** frontend/app/(ingest|search|memory|experiments)/page.tsx + components/* (many, but each page/component task can be split if needed)  
**Estimated scope:** Large — recommend splitting into 4 sub-tasks (one per page) if one agent

**Task 4.3: Progress / SSE or polling integration + global error handling in frontend**

**Description:** Add progress tracking component (progress bar + per-chunk table that updates live). Implement consistent error toast/banner using the API error shape. Add loading skeletons.

**Acceptance criteria:**
- [ ] Long-running ingest/search shows live progress without full page reload
- [ ] Any API error surfaces user-friendly message (code + message) + "Retry" where appropriate
- [ ] No unhandled promise rejections in console during normal flows

**Verification:**
- [ ] Simulate slow ingest → progress UI updates correctly
- [ ] Trigger validation error → toast shows exact message from backend

**Dependencies:** Task 4.2  
**Files:** frontend/components/ingest-progress.tsx, frontend/lib/api-client.ts (error interceptor), frontend/components/error-boundary.tsx or toast system  
**Estimated scope:** Small-Medium

### Checkpoint 4: Full v1 Platform Usable by Researcher

- [ ] All 4 workflows functional with rich observability
- [ ] Memory curation works
- [ ] Experiments page enables systematic comparison and learning
- [ ] Researcher can tinker with every parameter and immediately see metadata impact

---

### Phase 5: Polish, Testing, Documentation & Hardening

**Task 5.1: Comprehensive test suite (unit + integration + contract) + CI skeleton**

**Description:** Expand tests to cover all modules, happy + error paths, Neo4j interactions (testcontainers or dedicated test DB), frontend component tests (Vitest + Testing Library or Playwright e2e). Add contract tests that assert API matches OpenAPI spec. Add basic GitHub Actions or equivalent CI (lint, test, build, docker build).

**Acceptance criteria:**
- [ ] `pytest` full suite passes with good coverage on services/api
- [ ] Frontend tests pass
- [ ] Contract tests catch any drift between code and API_Interface_Design
- [ ] CI pipeline runs on push (or documented how to run locally)

**Verification:**
- [ ] Coverage report generated
- [ ] Fresh clone + `make test` or `docker compose run backend pytest` succeeds

**Dependencies:** All previous tasks  
**Files:** tests/**/*, frontend/__tests__ or e2e/, .github/workflows/ci.yml or equivalent, pyproject.toml (coverage config)  
**Estimated scope:** Medium

**Task 5.2: Documentation, README, researcher quickstart, troubleshooting**

**Description:** Write comprehensive README.md (setup, one-time commands, how to run experiments, how to interpret metadata, troubleshooting common issues like VRAM, model download). Add example experiment configs. Document known limitations (v1 standard paths only). Add ADR or decision log if needed.

**Acceptance criteria:**
- [ ] New researcher can follow README and have first experiment running in <30 min
- [ ] Common errors (CUDA OOM, model not found, Neo4j connection) have clear fixes documented
- [ ] Tinkering guide: "how to compare Recursive vs Semantic on same corpus" with screenshots or steps

**Verification:**
- [ ] Dry-run by someone unfamiliar with the codebase succeeds
- [ ] Docs link back to the design MD files for deeper reading

**Dependencies:** All implementation done  
**Files:** backend/README.md, frontend/README.md, docs/ or root docs folder, perhaps a /experiments/examples/ folder  
**Estimated scope:** Small-Medium

**Task 5.3: Performance baseline + simple hardening (rate limiting? basic input validation already done, logging levels, resource limits)**

**Description:** Record baseline timings for ingest/search on sample corpus. Add basic resource guards (max upload size, timeout on embedding). Ensure retry policies only on transient errors. Final security sweep per security-and-hardening principles (least privilege in Docker, no secrets in images, input validation at boundaries).

**Acceptance criteria:**
- [ ] Baseline numbers documented (e.g. "10k token doc LongText ingest: X ms on 3070 Ti")
- [ ] No obvious resource exhaustion paths left open
- [ ] Docker runs with reasonable memory/CPU limits

**Verification:**
- [ ] Run sample workload and record metrics
- [ ] Security lint (bandit or equivalent) clean or documented exceptions

**Dependencies:** Phase 4 complete  
**Files:** scripts/baseline.py or docs/performance.md, docker-compose overrides, core/config validation extensions  
**Estimated scope:** Small

### Final Checkpoint: v1.1 Ready for Researcher Use

- [ ] All acceptance criteria from design docs met
- [ ] Researcher can perform systematic RAG experimentation with full observability and comparison
- [ ] System is stable, documented, and ready for tinkering / extension (Late paths behind flags)
- [ ] Code review + manual end-to-end journey passes
- [ ] Ready to tag v1.1 and begin post-v1 planning

---

## Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| CUDA OOM on large documents or high batch | High (crashes ingest) | Medium | Enforce conservative chunk sizes in LongText path; batch size=1 for embedding; expose chunk size/overlap as config; monitor with nvidia-smi in docs |
| Embedding model load time or VRAM spikes | Medium (slow startup, instability) | Low | Preload in lifespan or worker; document exact VRAM usage of BGE-M3; offer smaller fallback model in config |
| Neo4j vector search perf degrades with many chunks | Medium (slow search) | Medium | Parent-level retrieval first (fewer vectors); HNSW params tuned in init script; index only on experiment subsets if needed; document corpus size limits for v1 |
| Inconsistent chunk counts / tokenization between methods | Low (confuses comparison) | Medium | Use same tokenizer everywhere; log exact token_count per chunk; add "tokenizer" field to metadata |
| Frontend state drift or TanStack Query cache issues after mutations | Medium (stale UI) | Low | Strict invalidation keys; optimistic updates only where safe; comprehensive e2e tests for workflows |
| Researcher misinterprets metadata (over-trusts numbers) | Low (bad science) | Medium | Clear labels + tooltips in UI; "what this number means" docs; emphasize that observability enables learning, not absolute truth |
| Scope creep into Late/Agentic features | High (delays v1, violates guardrail) | Medium | Strict adherence to "standard paths only"; any new branching behind feature flag + explicit ADR; plan review checkpoints |

---

## Open Questions (for human / researcher input before or during execution)

- What is the exact target chunk size + overlap % for the LongText sliding-window path in Slice 1? (Current design says ~30k tokens / 10% — confirm or adjust for BGE-M3 context window comfort.)
- Default chunkMethod and embeddingApproach for new experiments? (Recommend "Recursive" + "ChildChunk" as sensible starting point, but expose prominently.)
- Preferred progress mechanism for long jobs: SSE (real-time, more complex) or simple polling every 2-3s? (Frontend mapping assumes either; SSE preferred for better UX if worker supports.)
- Max document size / token limit for v1 ingest? (Protect against OOM and runaway jobs.)
- Any specific sample documents or benchmark queries the researcher wants pre-loaded for initial testing/comparison?
- Should side-by-side experiment comparison on Experiments page be simple (two columns) or more advanced (diff view of parameters + metrics)?

---

## Parallelization Opportunities

**Safe to parallelize (independent or after contract stable):**
- Frontend page implementation (Ingest page can start after Task 1.1 schemas + basic ingest API; other pages after their backend slices)
- Unit tests for already-implemented modules
- Documentation writing
- Performance baseline scripts
- Additional chunking strategy tests (once ChunkingModule interface stable)

**Must be sequential:**
- Neo4j schema/index creation (before any persistence)
- Core orchestrator + metadata (foundation for all slices)
- Database writes that change shared state

**Needs coordination:**
- API contract changes (define in schemas first, then both backend and frontend can implement)
- Model loading / GPU resource (coordinate backend + worker)

---

## Plan Verification (Before Starting Implementation)

- [x] Every task has clear, testable acceptance criteria (3+ bullets where possible)
- [x] Every task has explicit verification steps (tests, manual checks, commands)
- [x] Dependencies are identified and ordered correctly (foundation → vertical slices → polish)
- [x] No task is XL-sized without further breakdown (most are S/M; large ones noted to split)
- [x] Checkpoints exist after every phase so researcher can validate and decide to continue
- [x] Risks and open questions surfaced for discussion
- [x] Tinkering / Antifragility principles embedded (parameters exposed, metadata rich, researcher learns by doing)
- [x] Via Negativa respected (no v2 features in v1 tasks, no over-abstraction)

**Next step recommendation**: Review this plan with the researcher (or self-review), confirm Open Questions, then begin with Phase 0 (infrastructure is low-risk and unblocks everything). Execute one checkpoint at a time.

---

**End of Implementation Plan v1.1**
