# Docker Stack — RAG Lab v1.3

Reproducible Docker stack: **FastAPI backend + Next.js frontend + Neo4j 5.20 + Redis 7** with NVIDIA GPU passthrough. Targets **Windows Docker Desktop (WSL2)** and **Linux (NVIDIA Container Toolkit)** with a GTX 3070 Ti / 8 GB VRAM class GPU.

> Architecture decisions: see [`../upload/v1.3-docker-design-decision.md`](../upload/v1.3-docker-design-decision.md).
> Windows PowerShell commands: see [`../upload/v1.3-powershell-commands.md`](../upload/v1.3-powershell-commands.md).

---

## 1. Prerequisites

### GPU + driver

| Platform | Requirement |
|---|---|
| **Windows** | Docker Desktop (latest, WSL2 backend) + NVIDIA Windows driver (latest) + WSL2 Ubuntu distro + NVIDIA Container Toolkit installed **inside WSL2** |
| **Linux** | Docker Engine ≥ 23.0 + Docker Compose v2 + NVIDIA driver ≥ 550 + NVIDIA Container Toolkit |

Verify GPU passthrough before building:
```bash
docker run --rm --gpus all nvidia/cuda:13.3.0-devel-ubuntu26.04 nvidia-smi
```
If `nvidia-smi` fails inside the container, the NVIDIA Container Toolkit is not configured. On Windows, ensure Docker Desktop uses the WSL2 backend (Settings → Resources → WSL2 integration enabled).

### BuildKit

BuildKit is required (for cache mounts). It is **enabled by default** in:
- Docker Desktop ≥ 4.34
- Docker Engine ≥ 23.0

If using an older Docker, set `DOCKER_BUILDKIT=1` before `docker compose build`.

---

## 2. Build

From the **project root** (not this `docker/` dir):

```bash
# Copy env
cp docker/.env.example .env

# Build all 5 images (neo4j + redis pull; backend + api-worker + frontend build)
docker compose build
```

**Build args** (in `.env`):
- `DOWNLOAD_BGE=0` (default) — download only Jina v5 + Jina reranker v3.
- `DOWNLOAD_BGE=1` — also download BGE-M3 + BGE-reranker-base (enables the Settings toggle without re-pulling).

The backend Dockerfile is multi-stage (model-downloader → runtime) with BuildKit cache mounts on the HuggingFace + pip caches. A code-only rebuild skips re-downloading multi-GB model weights (cache hit).

---

## 3. One-time init

```bash
# Download models (Jina default; or set DOWNLOAD_BGE=1 for both families)
docker compose run --rm backend python scripts/download_models.py

# Initialize Neo4j schema (constraints + vector indexes 1024-dim cosine + fulltext)
docker compose run --rm backend python scripts/init_neo4j.py
```

Both are idempotent — safe to re-run.

---

## 4. Run

```bash
docker compose up -d          # start all services
docker compose ps             # verify all healthy
docker compose logs -f backend
```

| Service | Port | URL |
|---|---|---|
| Frontend (Next.js) | 3000 | http://localhost:3000 |
| Backend (FastAPI) | 8000 | http://localhost:8000 + `/docs` |
| Neo4j Browser | 7474 | http://localhost:7474 (bolt :7687, neo4j / P@ssw0rd) |
| Redis | 6379 | (no UI; `docker compose exec redis redis-cli MONITOR`) |

---

## 5. Stop / reset

```bash
docker compose down           # stop + remove containers (keep volumes)
docker compose down -v        # also drop neo4j_data + redis_data volumes
```

---

## 6. Frontend local development (host)

For frontend-only iteration without rebuilding the frontend image, run Next.js on the host:

```bash
# Install deps on the HOST (npm install — the host may have a different lockfile state)
npm install

# Start dev server (port 3000). The Dockerized backend must be running on :8000.
BACKEND_URL=http://localhost:8000 npm run dev
```

> **Docker build uses `npm ci`** (strict lockfile install for reproducibility). **Host dev uses `npm install`** (resolves to the current lockfile). Never run `npm install` inside the Docker builder — it breaks reproducibility. The `Dockerfile.frontend` uses `bun install --frozen-lockfile` (equivalent to `npm ci`) when `bun.lock` is present.

---

## 7. Switching embedding model (Jina ↔ BGE-M3)

Edit `.env`:
```env
EMBEDDING_MODEL=bge-m3
RERANKER_MODEL=bge-reranker-base
```
Then:
```bash
docker compose up -d --force-recreate backend api-worker
```
Both models produce 1024-dim vectors (Jina uses Matryoshka truncation to 1024). Re-ingest documents to regenerate vectors. See [`../upload/v1.3-embedding-migration.md`](../upload/v1.3-embedding-migration.md) for the full model-integration guide.

---

## 8. Running scripts inside the running container

The container has `PYTHONPATH=/app`, so scripts in `backend/scripts/` can import from `app.*` directly:

```bash
docker compose exec backend python scripts/init_neo4j.py    # re-run Neo4j init
docker compose exec backend python scripts/download_models.py   # re-run model download
```

To test a **code change** without rebuilding: add a volume mount to the `backend` service in `docker-compose.yml`:
```yaml
volumes:
  - ../backend:/app
```
Then `docker compose up -d --force-recreate backend` picks up edits live (dev only — don't use in production).
