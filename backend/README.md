# Local-First RAG Experimentation Platform v1.2 — FastAPI Backend

This is the **canonical RAG backend** per the directive: FastAPI (Python 3.12) +
Neo4j 5.x + Redis + BGE-M3 embeddings on GPU. The Next.js app is a thin proxy
that forwards `/api/v1/*` requests to this backend (see
`src/lib/rag/backend-client.ts`).

> Standard paths only — no Late/Agentic Chunking, no Structured Chat, no
> GraphRAG, no multi-user. v1 scope guardrail enforced.

## Stack

| Layer | Tech |
|---|---|
| Framework | FastAPI 0.115 + Uvicorn |
| Language | Python 3.12 |
| Database | Neo4j 5.26 (graph: Knowledge / KnowledgeChunk / UserQuery / Memory / MemoryCart / Experiment) |
| Job queue + progress | Redis 5.x (in-memory fallback for dev) |
| Embedding | BGE-M3 (`BAAI/bge-m3`, 1024-dim) via sentence-transformers |
| Reranker (optional) | BGE-reranker-base (`BAAI/bge-reranker-base`) cross-encoder |
| Validation | Pydantic v2 |
| Logging | stdlib logging → JSON lines |

## Directory structure

See `backend-directory-structure_v1.1.md` for the spec. This implementation
matches it exactly:

```
backend/
├── app/
│   ├── main.py                          # FastAPI factory + lifespan + global exception handler
│   ├── core/                            # config, logging, exceptions, constants
│   ├── api/v1/                          # router + experiments, documents, ingest, search, memory, jobs, dashboard, seed
│   ├── schemas/                         # Pydantic v2 models mirroring src/lib/rag/types.ts EXACTLY
│   ├── services/                        # orchestrator, chunking, embedding, retrieval, metadata (STRICT boundaries)
│   ├── models/                          # neo4j_models.py
│   ├── db/                              # neo4j_client, vector_index
│   ├── workers/                         # tasks, progress (Redis-backed)
│   └── utils/                           # tokenization, timing
├── scripts/                             # download_models.py, init_neo4j.py
├── tests/                               # empty per project rules
├── requirements.txt
├── pyproject.toml
└── README.md                            # this file
```

## Strict module boundaries (Backend §2)

| Module | Owns | Never |
|---|---|---|
| `ChunkingModule` | pure boundary detection | embeds, persists |
| `EmbeddingModule` | vectors only (BGE-M3) | chunks, persists |
| `RetrievalModule` | scores only (hybrid + rerank) | embeds, persists |
| `PipelineOrchestrator` | coordination + metadata + transactions + lifecycle | scores (delegates to RetrievalModule) |
| `MetadataService` | pure metadata factories | persists |
| `Neo4jClient` | typed CRUD + parameterized Cypher | embeds, scores |

## Construction notes (user requirements)

### #1 — float32 casting (EmbeddingModule)

On GPU, `sentence_transformers.SentenceTransformer.encode(...)` may return a
bfloat16 tensor. NumPy has **no native bfloat16 dtype** and will fail (or
silently produce wrong values via object arrays). The `EmbeddingModule`
ALWAYS converts to float32 on CPU before returning any vector:

```python
# ─── Construction note #1 (MANDATORY) ──────────────────────────────────────
# NumPy cannot handle bfloat16. Force the tensor to CPU + float32 before
# converting to a Python list.
emb_cpu = emb.detach().cpu().to(torch.float32)
outputs.extend(emb_cpu.tolist())
```

Applied on every encode path (GPU and CPU) in `services/embedding.py`.

### #2 — Adaptive α/β sweep (RetrievalModule)

Two fusion modes (per `SearchConfig.autoTuneWeights`):

- **Manual** (`autoTuneWeights=false`): `fused = alpha * vectorScore + beta * bm25Score`
  where `beta = 1 - alpha`, using the request's `hybridAlpha`.
- **Adaptive** (`autoTuneWeights=true`): sweep `alpha ∈ {0.1, 0.2, ..., 0.9}`,
  for each compute fused scores for all candidates, pick the alpha whose
  **TOP-1** result has the highest fused similarity. Return `bestAlpha` in
  `SearchMetadata`.

RRF (Reciprocal Rank Fusion) is also implemented as a documented alternative
(`_rrf_fuse`), but the weighted fusion is primary for v1.2 per construction
note #2.

### #5 — ChildChunk ingest refinement

Per the user's explicit requirement: "ChildChunk only allow the longtext
embedded document to use the longtext embedding to do the child chunk."

`PipelineOrchestrator.ingest_child_chunk` implements:

1. **FIRST** embed the FULL document with the LongText embedding → creates ONE
   `:Knowledge` parent node carrying the long-text vector (the **context vector**).
   Parent's `embedding_method="LongText"`.
2. **THEN** chunk the document with the chosen ChildChunk method
   (Recursive / Semantic / Structure-Aware).
3. **THEN** embed each child chunk with the ChildChunk embedding method.
4. **Persist BOTH** the parent LongText vector AND the child chunk vectors
   (parent-child hierarchy via `(:Knowledge)-[:HAS_CHUNK]->(:KnowledgeChunk)`).
   Children's `embedding_method="ChildChunk"`.
5. The `ExperimentRun` records `embedding_approach="ChildChunk"` but the
   parent's long-text embedding is **always present**.

**ChildChunk = LongText parent embedding + N child chunk embeddings.**
The parent LongText vector is the context; child vectors are the retrieval
targets (the HNSW index on `:KnowledgeChunk` serves them).

## REST contract

All endpoints are mounted under `/api/v1` and mirror the TS types in
`src/lib/rag/types.ts` EXACTLY (camelCase keys, optional fields, score types).
The Next.js proxy in `src/app/api/v1/*/route.ts` forwards requests unchanged.

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/experiments` | Create an experiment record |
| GET | `/api/v1/experiments` | List (paginated, `?kind=ingest\|search`, `?page`, `?pageSize`) |
| GET | `/api/v1/experiments/{id}` | Get one |
| GET | `/api/v1/experiments/{id}/chunks` | List chunks (observability) |
| POST | `/api/v1/documents` | Upload (JSON `{filename,text,contentType?}` OR multipart `file`) |
| GET | `/api/v1/documents` | List (paginated) |
| DELETE | `/api/v1/documents/{id}` | Delete by source_file |
| POST | `/api/v1/ingest` | Start ingest → `202 {jobId, experimentId, status}` |
| GET | `/api/v1/ingest/{jobId}/status` | Poll job status |
| POST | `/api/v1/search` | Start search → `202 {jobId, searchId, status}` |
| GET | `/api/v1/searches/history` | List past searches (paginated) |
| GET | `/api/v1/memories` | List memories (paginated, `?experimentId`) |
| POST | `/api/v1/memories` | Manually create a memory |
| POST | `/api/v1/memory-carts` | Create a cart |
| GET | `/api/v1/memory-carts` | List carts |
| GET | `/api/v1/memory-carts/{id}` | Get one cart with embedded memories |
| PATCH | `/api/v1/memory-carts/{id}` | Update name/description OR set/add memory ids |
| GET | `/api/v1/jobs/{jobId}` | Generic job status (ingest or search) |
| GET | `/api/v1/dashboard` | Stats + recent experiments + recent searches + system info |
| POST | `/api/v1/seed` | Seed 4 sample markdown docs into Neo4j |
| GET | `/health` | Health check (`{status:"ok"}`) |

### Error contract

Every non-2xx response:

```json
{ "error": { "code": "VALIDATION_ERROR", "message": "...", "details": {} } }
```

Error codes (per `error-handling-retry-strategy_v1.1.md` §1):
`VALIDATION_ERROR` (422), `NOT_FOUND` (404), `INGEST_FAILED` (500),
`EMBEDDING_FAILED` (502), `NEO4J_ERROR` (500), `SEARCH_FAILED` (500),
`RERANK_FAILED` (502), `JOB_NOT_FOUND` (404), `INTERNAL_ERROR` (500).

Stack traces are NEVER leaked to clients — they are logged server-side with
structured fields (`experiment_id`, `stage`, `error_code`, `retry_count`).

## Configuration

All config is env-driven (Pydantic Settings in `app/core/config.py`). Defaults
match `infrastructure-environment-spec_v1.1.md` §5.

| Env var | Default | Description |
|---|---|---|
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j bolt URI |
| `NEO4J_USER` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | `P@ssw0rd` | Neo4j password |
| `NEO4J_DATABASE` | `neo4j` | Target database |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis URL (job queue + progress) |
| `MODEL_PATH` | `/app/models` | Root dir for downloaded models |
| `CUDA_VISIBLE_DEVICES` | `0` | GPU id(s) or `-1` for CPU-only |
| `EMBEDDING_DIM` | `1024` | BGE-M3 output dim |
| `LOG_LEVEL` | `INFO` | Logging level |
| `FRONTEND_ORIGIN` | `*` | CORS origin(s) for the Next.js frontend |
| `ENABLE_RERANKER` | `true` | Load BGE-reranker-base on startup |
| `JOB_TTL_SECONDS` | `86400` | Redis TTL for completed/failed jobs |

## Running

### Local dev (without Docker)

```bash
# 1. Install Python 3.12 + dependencies
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Start Neo4j + Redis (e.g. via docker)
docker run -d --name neo4j -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/P@ssw0rd neo4j:5.26-community
docker run -d --name redis -p 6379:6379 redis:7-alpine

# 3. One-time: download models + init Neo4j schema
python scripts/download_models.py
python scripts/init_neo4j.py

# 4. Run the API
MODEL_PATH=./models uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Docker (production-style)

See `/docker/Dockerfile.backend` (multi-stage: model-downloader → CUDA runtime).
The `docker/docker-compose.yml` (in the repo root) wires up neo4j + redis +
backend + api-worker + frontend.

```bash
docker compose build
docker compose run --rm backend python scripts/download_models.py
docker compose run --rm backend python scripts/init_neo4j.py
docker compose up -d
```

## One-time setup scripts

| Script | Purpose |
|---|---|
| `scripts/download_models.py` | Download `BAAI/bge-m3` (+ optional `BAAI/bge-reranker-base`) into `MODEL_PATH` via huggingface_hub. Idempotent. |
| `scripts/init_neo4j.py` | Run all constraint + vector index + fulltext index Cypher from `neo4j-schema-v1.1.md` against the configured Neo4j. Idempotent. Prints a per-statement status table. |

## Pipeline overview

### Ingest — LongText

```
Document → ChunkingModule.chunk_long_text (sliding window ~8k tokens, 10% overlap)
         → for each window:
             EmbeddingModule.embed_with_retry (LongText)
             Neo4jClient.create_knowledge (window IS its own :Knowledge node)
             progress callback emits ChunkMetadata
         → Neo4jClient.update_experiment_status (completed)
```

### Ingest — ChildChunk (USER REQUIREMENT #5)

```
Document → EmbeddingModule.embed_with_retry (LongText, FULL doc)
         → Neo4jClient.create_knowledge (ONE parent :Knowledge with long-text vector)
         → ChunkingModule.determine_boundaries (Recursive / Semantic / Structure-Aware)
         → for each child boundary:
             EmbeddingModule.embed_with_retry (ChildChunk)
             Neo4jClient.create_chunk (:KnowledgeChunk + (:Knowledge)-[:HAS_CHUNK]->(:KnowledgeChunk))
             progress callback emits ChunkMetadata
         → Neo4jClient.update_experiment_status (completed)
```

### Search

```
rawQuery → EmbeddingModule.embed_with_retry (LongText)
         → Neo4jClient.create_user_query (:UserQuery)
         → RetrievalModule.hybrid_search:
             1. Neo4jClient.vector_search_chunks (HNSW cosine on :KnowledgeChunk)
             2. optional Neo4jClient.bm25_search_chunks (fulltext)
             3. fusion: manual (alpha*vector + beta*bm25) OR adaptive sweep
             4. optional reranker (BGE-reranker-base) on top-N
         → for each result:
             Neo4jClient.create_memory (:Memory + :UserQuery-[:TRIGGERED]->:Memory-[:RETRIEVED]->:KnowledgeChunk)
         → Neo4jClient.update_experiment_status (completed, with best_alpha)
         → return SearchResponse (results + metadata)
```

## Testing

Per project rules, no test code is written. The `tests/` directory is kept
with just `__init__.py` so future tests can be added without restructuring.

## License

MIT
