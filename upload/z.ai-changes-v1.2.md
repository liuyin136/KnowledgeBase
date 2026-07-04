# z.ai Changes v1.2 — Real Stack Pivot (FastAPI + Neo4j + Docker)

**Version**: 1.2
**Date**: 2026-07-04
**Status**: Implemented
**Supersedes**: v1.1 sandbox adaptation (Prisma/SQLite + z-ai-web-dev-sdk)
**Aligned with**: Backend_Design_Scope_v1.1.md, API_Interface_Design_v1.1.md, backend-directory-structure_v1.1.md, neo4j-schema-v1.1.md, error-handling-retry-strategy_v1.1.md, Frontend_Workflow_Mapping_v1.1.md, infrastructure-environment-spec_v1.1.md

---

## 1. Motivation

v1.1 was a faithful sandbox adaptation of the directive, but it substituted the real stack
(FastAPI + Neo4j + Redis + GPU + BGE-M3) with Next.js + Prisma/SQLite + z-ai-web-dev-sdk
because the sandbox only runs a single Next.js app on port 3000. v1.2 pivots to the **real
directive stack** targeting **Windows Server deployment** with Docker, while keeping the
Next.js app as the frontend + thin proxy layer.

The sandbox still cannot run Neo4j/FastAPI/GPU — that is accepted ("even the sandbox cannot
simulate"). The code is now correct for the real stack; the frontend renders gracefully
with clear "backend offline" states when the Docker stack is absent.

---

## 2. Summary of Changes

| # | Change | Rationale |
|---|--------|-----------|
| 1 | **Removed Prisma/SQLite + z-ai-web-dev-sdk** | Real stack uses Neo4j (graph) + FastAPI (BGE-M3 on GPU). The sandbox-adapted persistence + SDK are no longer needed. |
| 2 | **Added FastAPI backend** (`/backend`, Python 3.12) | The canonical RAG engine per backend-directory-structure_v1.1.md. Owns Neo4j writes, BGE-M3 embeddings, hybrid search, reranker, job queue. |
| 3 | **Added Docker setup** (`/docker`) | One-command reproducible deployment per infrastructure-environment-spec_v1.1.md. Multi-stage Dockerfiles + docker-compose (neo4j + redis + backend + api-worker + frontend) with NVIDIA GPU passthrough. |
| 4 | **Neo4j schema initiation** | `backend/scripts/init_neo4j.py` + `POST /api/v1/neo4j/init` (Next.js route using neo4j-driver) run all constraints + vector indexes (1024-dim cosine) + fulltext indexes from neo4j-schema-v1.1.md. Idempotent. |
| 5 | **Next.js → thin proxy** | All `/api/v1/*` routes now proxy to `${BACKEND_URL}/api/v1/*` (FastAPI). Added `neo4j-driver` for direct read + init. Graceful 503 `BACKEND_UNAVAILABLE` when backend is down. |
| 6 | **ChildChunk ingest refinement** | ChildChunk now ALWAYS creates a LongText parent embedding (full-doc context vector) + child chunk embeddings. Parent `:Knowledge` node carries `embedding_method="LongText"`; children carry `embedding_method="ChildChunk"`. Both vectors persist (parent-child hierarchy). |
| 7 | **Experiments MD editor** | Added `@mdxeditor/editor` to the Experiments detail view with a raw/rendered toggle. Researcher can edit the reconstructed source document and save as a new document (non-destructive). |
| 8 | **Memory Cart larger inspection area** | Redesigned: 260px carts sidebar + dominant inspection pane with resizable split (chunk text 62% / scores 38%) + keyboard navigation. |
| 9 | **Removed sandbox cache** | Deleted `db/custom.db`, `prisma/`, `src/lib/db.ts`. No SQLite, no in-memory caches. The app talks to Neo4j (real) or shows offline. |

---

## 3. Architecture (v1.2)

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser (user)                                                  │
│    └─ Next.js SPA (single route /)                               │
│       └─ TanStack Query → fetch('/api/v1/*')                     │
└──────────────────────────┬──────────────────────────────────────┘
                           │ same-origin
┌──────────────────────────▼──────────────────────────────────────┐
│  Next.js (port 3000) — frontend + thin proxy                     │
│    src/app/api/v1/* → proxyToBackend(BACKEND_URL)                │
│    src/lib/rag/neo4j.ts — direct read + init (neo4j-driver)      │
│    src/lib/rag/backend-client.ts — proxy + health                │
└──────────────────────────┬──────────────────────────────────────┘
                           │ BACKEND_URL=http://backend:8000
┌──────────────────────────▼──────────────────────────────────────┐
│  FastAPI backend (port 8000) — the real RAG engine               │
│    app/services/orchestrator.py — PipelineOrchestrator           │
│    app/services/chunking.py — ChunkingModule (pure boundaries)   │
│    app/services/embedding.py — EmbeddingModule (BGE-M3, GPU)     │
│    app/services/retrieval.py — RetrievalModule (hybrid + adapt)  │
│    app/services/metadata.py — MetadataService                    │
│    app/db/neo4j_client.py — Neo4j driver + Cypher                │
│    app/workers/ — background ingest/search (Redis-backed)        │
└────────┬──────────────────────┬──────────────────────────────────┘
         │ bolt://              │ redis://
┌────────▼─────────┐   ┌────────▼─────────┐
│  Neo4j 5.20      │   │  Redis 7         │
│  (graph + HNSW   │   │  (job queue +    │
│   + fulltext)    │   │   progress)      │
└──────────────────┘   └──────────────────┘
```

**Module boundaries (unchanged from v1.1, now in Python):**
- `ChunkingModule` → ONLY finds boundaries. Never embeds.
- `EmbeddingModule` → ONLY produces vectors. Never chunks.
- `RetrievalModule` → ONLY scores. Never embeds/persists.
- `PipelineOrchestrator` → owns coordination + metadata + transactions + lifecycle.

---

## 4. Construction Notes (carried forward)

### #1 — float32 casting (embedding)
```python
# app/services/embedding.py
# NumPy cannot handle bfloat16. Force the tensor to CPU + float32 before
# converting to a Python list.
emb_cpu = emb.detach().cpu().to(torch.float32)
outputs.extend(emb_cpu.tolist())
```
Applied on EVERY encode path (GPU and CPU). BGE-M3 may output bfloat16 on GPU;
this cast prevents numpy dtype errors in downstream cosine similarity.

### #2 — Adaptive α/β sweep (hybrid search)
```python
# app/services/retrieval.py — _adaptive_fuse()
# Sweep alpha ∈ {0.1, 0.2, ..., 0.9}; for each, compute fused scores
# (alpha*vector + beta*bm25, beta = 1 - alpha); pick the alpha whose
# TOP-1 result has the highest fused similarity. Return bestAlpha.
```
Surfaced as `SearchMetadata.bestAlpha` when `SearchConfig.autoTuneWeights=true`.
Manual mode uses the request's `hybridAlpha` directly.

### ChildChunk = LongText parent + child chunks (user requirement #5)
```python
# app/services/orchestrator.py — ingest_child_chunk()
# 1. FIRST embed the FULL document with LongText → :Knowledge parent node
#    (embedding_method="LongText", the context vector).
# 2. THEN chunk the document (Recursive/Semantic/Structure-Aware).
# 3. THEN embed each child chunk (embedding_method="ChildChunk").
# 4. Persist BOTH vectors via (:Knowledge)-[:HAS_CHUNK]->(:KnowledgeChunk).
```
The parent LongText vector is ALWAYS present in a ChildChunk experiment — it is
the context vector. This makes LongText-vs-ChildChunk comparison meaningful:
both approaches share the same parent context; ChildChunk adds per-chunk precision.

---

## 5. File Structure (v1.2)

```
/home/z/my-project/
├── backend/                          # NEW — FastAPI backend (Python 3.12)
│   ├── app/
│   │   ├── main.py                   # FastAPI factory + lifespan + global exception handler
│   │   ├── core/{config,logging,exceptions,constants}.py
│   │   ├── api/v1/{router,experiments,documents,ingest,search,memory,jobs,dashboard,seed}.py
│   │   ├── schemas/{common,experiment,document,ingest,search,memory}.py
│   │   ├── services/{orchestrator,chunking,embedding,retrieval,metadata}.py
│   │   ├── models/neo4j_models.py
│   │   ├── db/{neo4j_client,vector_index}.py
│   │   ├── workers/{tasks,progress}.py
│   │   └── utils/{tokenization,timing}.py
│   ├── scripts/{download_models,init_neo4j}.py
│   ├── requirements.txt
│   ├── pyproject.toml
│   └── README.md
├── docker/                           # NEW — Docker infrastructure
│   ├── Dockerfile.backend            # multi-stage: model-downloader → runtime (CUDA)
│   ├── Dockerfile.frontend           # multi-stage: builder → runner (standalone)
│   ├── docker-compose.yml            # neo4j + redis + backend + api-worker + frontend
│   ├── .env.example
│   └── README.md                     # one-command setup + Windows Server notes
├── docker-compose.yml                # thin include: → docker/docker-compose.yml
├── .dockerignore
├── src/
│   ├── app/
│   │   ├── page.tsx                  # SPA shell (5 views via Zustand)
│   │   ├── layout.tsx
│   │   └── api/v1/                   # ALL routes → thin proxies to BACKEND_URL
│   │       ├── experiments/...       # proxy
│   │       ├── documents/...         # proxy
│   │       ├── ingest/...            # proxy
│   │       ├── search/...            # proxy
│   │       ├── searches/history/     # proxy
│   │       ├── memories/             # proxy
│   │       ├── memory-carts/...      # proxy
│   │       ├── jobs/...              # proxy
│   │       ├── dashboard/            # proxy + Neo4j/backend health
│   │       ├── seed/                 # proxy
│   │       └── neo4j/{health,init}/  # NEW — direct Neo4j (neo4j-driver)
│   ├── lib/
│   │   ├── api-client.ts             # typed client + isBackendOffline helper
│   │   └── rag/
│   │       ├── types.ts              # contract (unchanged)
│   │       ├── constants.ts
│   │       ├── errors.ts
│   │       ├── utils.ts
│   │       ├── vectors.ts
│   │       ├── chunking.ts           # kept (reference impl + demo)
│   │       ├── metadata.ts
│   │       ├── api-helpers.ts
│   │       ├── backend-client.ts     # NEW — proxyToBackend + backendHealth
│   │       └── neo4j.ts              # NEW — neo4j-driver singleton + read/init
│   ├── components/
│   │   ├── rag/
│   │   │   ├── views/{dashboard,ingest,search,memory,experiments}-view.tsx
│   │   │   ├── shared/
│   │   │   │   ├── view-header.tsx
│   │   │   │   ├── backend-offline.tsx       # NEW — reusable offline state
│   │   │   │   └── markdown-editor.tsx       # NEW — MDXEditor wrapper
│   │   │   ├── sidebar.tsx
│   │   │   └── providers.tsx
│   │   └── ui/                       # shadcn (unchanged)
│   └── store/use-ui-store.ts
├── package.json                      # removed @prisma/client, prisma, z-ai-web-dev-sdk; added neo4j-driver
└── worklog.md                        # full history
```

**Removed (v1.1 sandbox artifacts):**
- `prisma/` (schema.prisma)
- `db/` (custom.db — the sandbox cache)
- `src/lib/db.ts` (Prisma client)
- `src/lib/rag/store.ts` (Prisma data-access → moved to backend)
- `src/lib/rag/orchestrator.ts` (moved to backend)
- `src/lib/rag/retrieval.ts` (moved to backend)
- `src/lib/rag/jobs.ts` (moved to backend)
- `src/lib/rag/embedding.ts` (LocalHash → replaced by BGE-M3 in backend)
- `src/lib/rag/bm25.ts` (moved to backend retrieval)
- `@prisma/client`, `prisma`, `z-ai-web-dev-sdk` from package.json

---

## 6. REST API Contract (unchanged shape, new transport)

The API shape is IDENTICAL to v1.1 (API_Interface_Design_v1.1.md). The only difference:
requests are now proxied Next.js → FastAPI instead of handled by Prisma. New endpoints:

- `GET /api/v1/neo4j/health` — Neo4j connectivity check (direct, via neo4j-driver)
- `POST /api/v1/neo4j/init` — run all Neo4j constraints + vector indexes + fulltext (direct)
- `GET /health` (backend) — FastAPI health (used by Next.js `backendHealth()`)

**Error contract** (unchanged): all non-2xx → `{"error":{"code","message","details"?}}`.
New error codes: `BACKEND_UNAVAILABLE` (503, BACKEND_URL unset), `BACKEND_UNREACHABLE`
(503, network error), `NEO4J_UNAVAILABLE` (503, Neo4j down).

---

## 7. Docker Setup (one-command)

```bash
# From project root
docker compose build                              # build all 5 images
docker compose run --rm backend python scripts/download_models.py   # one-time: BGE-M3
docker compose run --rm backend python scripts/init_neo4j.py        # one-time: schema
docker compose up -d                              # start everything
docker compose ps                                 # verify healthy
curl http://localhost:8000/health                 # backend
curl http://localhost:3000/api/v1/neo4j/health    # Neo4j via frontend
```

**Services** (docker/docker-compose.yml):
- `neo4j:5.20-community` (APOC, 7474+7687, volume)
- `redis:7-alpine` (6379, volume)
- `backend` (8000, GPU, depends neo4j+redis healthy)
- `api-worker` (GPU, `python -m app.workers.worker`, depends redis+backend)
- `frontend` (3000, `BACKEND_URL=http://backend:8000`, depends backend healthy)

**Windows Server notes** (full details in `docker/README.md`):
- Use WSL2 Ubuntu distro or Hyper-V Linux VM (Docker EE on Windows Server doesn't support `--gpus all` natively).
- NVIDIA driver ≥ 551.61 (Windows) / 550.54.14 (Linux) for CUDA 12.4.
- NVIDIA Container Toolkit must be installed + `nvidia` runtime configured.

---

## 8. Frontend Behavior in Offline State (sandbox)

When `BACKEND_URL` is unset (sandbox) or the backend is unreachable:
- `GET /api/v1/dashboard` returns a health-only payload (stats zeros, health offline).
- All other `/api/v1/*` return 503 `BACKEND_UNAVAILABLE`.
- The frontend detects this via `isBackendOffline(err)` and shows a reusable
  `<BackendOffline>` component (amber banner + retry + docker-compose hint +
  "Check Neo4j health" link) instead of crashing.
- The Dashboard shows a prominent "Backend services offline" banner + System
  Connections cards (FastAPI + Neo4j status) + an "Init Neo4j schema" button
  (calls `POST /api/v1/neo4j/init` once Neo4j is up).
- The MD editor in Experiments + the larger Memory Cart inspection area are
  fully visible/explorable (the MD editor works client-side on reconstructed
  chunk text; the Memory Cart layout is visible with empty/offline states).

This satisfies "even the sandbox cannot simulate" — the UI is reviewable while
the real stack runs in Docker.

---

## 9. v1 Scope Guardrail (unchanged)

v1.2 preserves the guardrail: **standard paths only**.
- NO Late Chunking, NO Agentic Chunking
- NO Structured Chat
- NO GraphRAG
- NO multi-user features

All extensibility for post-v1 paths is prepared via clean module structure
(new files under `services/` behind feature flags) — the orchestrator + metadata
contract remain stable.

---

## 10. Verification

- **Next.js**: `bun run lint` → 0 errors. `bunx tsc --noEmit` → 0 errors (RAG platform code).
- **Backend**: `python3 -m compileall app scripts` → exit 0. FastAPI TestClient: `/health` 200, validation 422, all 21 routes match spec.
- **agent-browser**: Dashboard renders with offline banner + health cards; Ingest/Search/Memory/Experiments views show `<BackendOffline>` gracefully; no console errors; no crashes.
- **Construction notes**: #1 (float32 cast) verified in `backend/app/services/embedding.py`; #2 (adaptive α/β sweep) verified in `backend/app/services/retrieval.py`; ChildChunk parent LongText embedding verified in `backend/app/services/orchestrator.py`.

---

**End of z.ai Changes v1.2**
