# Task 3 (v1.2 pivot) — Docker infrastructure

**Agent**: full-stack-developer (Docker infrastructure)
**Task ID**: 3
**Files created**:
- `docker/Dockerfile.backend`
- `docker/Dockerfile.frontend`
- `docker/docker-compose.yml`
- `docker/.env.example`
- `docker/README.md`
- `docker-compose.yml` (root, thin `include:` wrapper)
- `.dockerignore` (root)
- `backend/.dockerignore` (backend build context)

## What was built

### `docker/Dockerfile.backend` — multi-stage
- **Stage 1 `model-downloader`** (`python:3.12-slim`):
  - Installs `git-lfs` + `huggingface_hub`.
  - Inline download script (no dependency on `backend/scripts/` existing yet)
    snapshots `BAAI/bge-m3` + `BAAI/bge-reranker-base` into `/app/models/<name>/`.
  - Build arg `DOWNLOAD_RERANKER=1` toggles the reranker (~1 GB).
  - BuildKit cache mount on `/root/.cache/huggingface` for resume on rebuild.
  - Skips `.msgpack` / `.h5` / ONNX variants (only safetensors + tokenizer).
- **Stage 2 `runtime`** (`nvidia/cuda:12.4.1-runtime-ubuntu22.04`):
  - **Documented deviation from spec**: uses `-runtime-` not `-devel-` (smaller,
    no `nvcc` needed — PyTorch ships cu121 wheels). Choice explained inline.
  - Installs Python 3.12 from deadsnakes + minimal system deps
    (`build-essential`, `libgomp1`, `curl`, `git`, `libgl1`, `libglib2.0-0`).
  - Copies `requirements.txt*` first (tolerates missing file via wildcard glob)
    with a minimal pin fallback so the image builds even if the backend agent
    hasn't shipped `requirements.txt` yet.
  - Copies models from stage 1 → `/app/models`, then copies backend code.
  - `ENV CUDA_VISIBLE_DEVICES=0`, `MODEL_PATH=/app/models`.
  - `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]`.
  - `HEALTHCHECK` hits `GET /health` every 15s.

### `docker/Dockerfile.frontend` — multi-stage, standalone
- **Stage 1 `builder`** (`node:22-alpine` + bun 1.1.42):
  - `bun install --frozen-lockfile` (falls back to `npm ci` if `bun.lock` absent).
  - Sanity-check greps `next.config.*` for `output: 'standalone'` — fails build
    loudly if it's missing.
  - `bun run build` (or `npx next build` fallback).
- **Stage 2 `runner`** (`node:22-alpine`):
  - Copies `.next/standalone` + `.next/static` + `public/`.
  - `USER node` (non-root).
  - `ENV NODE_ENV=production`, `BACKEND_URL=http://backend:8000`,
    `NEXT_PUBLIC_BACKEND_URL=` (empty by design — same-origin proxy).
  - `CMD ["node", "server.js"]`, `EXPOSE 3000`.

### `docker/docker-compose.yml` — 5 services
- **neo4j**: `neo4j:5.20-community`, APOC plugin, ports 7474+7687,
  `NEO4J_AUTH=neo4j/P@ssw0rd`, volume `neo4j_data:/data`, healthcheck on `:7474`.
- **redis**: `redis:7-alpine`, port 6379, AOF persistence, volume `redis_data:/data`,
  healthcheck via `redis-cli ping`.
- **backend**: build context `../backend` + dockerfile `../docker/Dockerfile.backend`,
  port 8000, env (`NEO4J_URI=bolt://neo4j:7687`, `REDIS_URL=redis://redis:6379/0`,
  `MODEL_PATH=/app/models`, `CUDA_VISIBLE_DEVICES=0`, `LOG_LEVEL`, `FRONTEND_ORIGIN=*`,
  `EMBEDDING_DIM=1024`, `EMBEDDING_MODEL=BAAI/bge-m3`), `depends_on` neo4j + redis
  with `condition: service_healthy`, GPU reservation, healthcheck.
- **api-worker**: same build as backend, `command: python -m app.workers.worker`,
  same env + GPU, `depends_on` redis + backend (healthy). Adds `RQ_QUEUE_NAME` +
  `WORKER_CONCURRENCY=1` (BGE-M3 + 8 GB VRAM = 1 concurrent job).
- **frontend**: build context `..` + dockerfile `docker/Dockerfile.frontend`,
  port 3000, env `BACKEND_URL=http://backend:8000`, `NEXT_PUBLIC_BACKEND_URL=`,
  `depends_on` backend (healthy).
- Named volumes: `neo4j_data`, `redis_data`. Network: `default` (bridge).

### `docker/.env.example` — per infra spec §5
All 11 vars (Neo4j, Redis, MODEL_PATH, LOG_LEVEL, FRONTEND_ORIGIN,
CUDA_VISIBLE_DEVICES, EXPERIMENT_STORAGE_PATH, BACKEND_URL,
NEXT_PUBLIC_BACKEND_URL, EMBEDDING_DIM, EMBEDDING_MODEL) + `DOWNLOAD_RERANKER`
build-time toggle.

### `docker/README.md`
- File map, host prerequisites (Linux + Windows Server paths table),
  one-command setup (build → optional model download → init_neo4j → up -d → verify),
  service overview table, env var reference, multi-stage rationale, 7 troubleshooting
  sections (CUDA, Neo4j auth, model download, port conflicts, hung `run --rm`,
  502 proxy, standalone-output sanity check), model update + backup/restore
  recipes, tear-down.

### Root `docker-compose.yml`
Thin wrapper: `include: [docker/docker-compose.yml]`. Lets users run
`docker compose up -d` from the project root without `-f`.

### `.dockerignore` (root)
Excludes `node_modules`, `.next`, `.git`, `tool-results`, `agent-ctx`,
`download`, `examples`, `docker` (build artifacts), `backend` (built separately),
local `.env`, `.db`, etc.

### `backend/.dockerignore`
Excludes `__pycache__`, `.pytest_cache`, `.venv`, `models/` (host dev downloads
that would bloat the image by ~2.4 GB), `*.safetensors` / `*.bin` / `*.onnx`,
`tests`, `experiments` (run artifacts), IDE noise, `.env`.

## Verification
- `next.config.ts` already has `output: "standalone"` (verified — no change needed).
- File tree confirmed: `docker/` has 5 files; root has `docker-compose.yml` +
  `.dockerignore`; `backend/.dockerignore` exists.
- Did NOT run `docker build` (no Docker daemon in sandbox, per task constraint).
- Compose file syntax follows v2 spec (uses `include:`, `deploy.resources.reservations.devices`,
  `depends_on.condition: service_healthy`).

## Notes for downstream agents
- **Backend agent**: the Dockerfile assumes `backend/requirements.txt` exists
  at build time. If absent, a minimal pin is written automatically. The fallback
  pin includes `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`,
  `neo4j`, `redis`, `rq`, `sentence-transformers`, `transformers`, `torch`,
  `numpy`, `python-multipart`, `httpx`, `tenacity`, `structlog`. Pin versions
  to taste in your `requirements.txt` to override.
- **Backend agent**: `scripts/download_models.py` and `scripts/init_neo4j.py`
  are referenced in the README's setup commands. They must exist and be
  idempotent. The Dockerfile already downloads BGE-M3 + reranker at build
  time, so `download_models.py` at runtime is OPTIONAL (only for refreshes).
- **Backend agent**: the api-worker entry point is `python -m app.workers.worker`.
  If you implement RQ, that module should `from rq import Worker, Queue, Connection`
  and `Worker([Queue('default')], connection=redis_conn).work()`. The
  `RQ_QUEUE_NAME=default` + `WORKER_CONCURRENCY=1` env vars are wired in compose.
- **Frontend agent**: the Next.js server proxies `/api/v1/*` to
  `http://backend:8000` server-side. `NEXT_PUBLIC_BACKEND_URL` is intentionally
  empty — keep it that way. The current `src/lib/rag/backend-client.ts` calls
  relative paths, which is correct for this proxy pattern; just make sure
  no client code reads `NEXT_PUBLIC_BACKEND_URL` to construct absolute URLs.
- **Windows Server caveat**: Docker EE on Windows Server does NOT support
  `--gpus all` natively. Recommend WSL2 Ubuntu distro or a Hyper-V Linux VM
  with PCI passthrough. Documented in `docker/README.md` §2.2.
- **GPU passthrough**: declared via `deploy.resources.reservations.devices`
  (Compose v2 + NVIDIA Container Toolkit). On a host without NVIDIA GPU,
  backend + api-worker will fail to start — remove that stanza for CPU-only mode.
