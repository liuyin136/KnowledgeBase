# RAG Lab v1.3 — Local-First RAG Experimentation Platform

A local-first RAG experimentation platform for systematically comparing embedding approaches (LongText vs ChildChunk) and chunking methods (Recursive / Semantic / Structure-Aware) via a tunable hybrid search pipeline (vector + BM25 + adaptive α/β sweep + optional reranker) with parent-child awareness — running on Windows Docker Desktop + WSL2 + NVIDIA GPU (GTX 3070 Ti class).

**Stack**: FastAPI (Python 3.12) + Neo4j 5.20 + Redis 7 + Next.js 16. Default embedding: `jinaai/jina-embeddings-v5-text-small`. Default reranker: `jinaai/jina-reranker-v3`. BGE-M3 available as a toggle.

---

## Build & Run

### Prerequisites

**Windows**: Docker Desktop (latest, WSL2 backend) + NVIDIA Windows driver (latest) + WSL2 Ubuntu distro + [NVIDIA Container Toolkit in WSL2](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).

**Linux**: Docker Engine ≥ 23.0 + Docker Compose v2 + NVIDIA driver + NVIDIA Container Toolkit.

Verify GPU passthrough before building:
```bash
docker run --rm --gpus all nvidia/cuda:13.3.0-devel-ubuntu26.04 nvidia-smi
```

### One-time setup (from project root)

```bash
# 1. Copy env
cp docker/.env.example .env

# 2. Build all images (BuildKit is default in Docker Desktop ≥ 4.34)
docker compose build

# 3. Download models (Jina v5 + Jina reranker v3 by default)
#    Set DOWNLOAD_BGE=1 in .env to also fetch BGE-M3 + BGE-reranker for the toggle.
docker compose run --rm backend python scripts/download_models.py

# 4. Initialize Neo4j schema (constraints + vector indexes + fulltext)
docker compose run --rm backend python scripts/init_neo4j.py

# 5. Start everything
docker compose up -d

# 6. Verify
docker compose ps
curl http://localhost:8000/health
```

### Endpoints

| Service | URL | Purpose |
|---|---|---|
| Frontend | http://localhost:3000 | RAG Lab UI (Dashboard, Ingest, Search, Memory, Experiments, Settings) |
| Backend | http://localhost:8000 | FastAPI REST API + `/docs` (Swagger) |
| Neo4j Browser | http://localhost:7474 | Graph DB admin (bolt://localhost:7687, neo4j / P@ssw0rd) |

### Common commands

```bash
docker compose logs -f backend      # tail logs
docker compose down                 # stop (keep volumes)
docker compose down -v              # stop + drop data volumes
docker compose up -d --force-recreate backend api-worker   # apply env changes
```

---

## Frontend local development (host, outside Docker)

For frontend-only iteration, run Next.js on the host with the backend in Docker:

```bash
# Install deps on the HOST (npm install — NOT npm ci; the host may have different lockfile state)
npm install

# Start dev server (port 3000). BACKEND_URL points to the Dockerized backend.
BACKEND_URL=http://localhost:8000 npm run dev
```

> **Note**: The Docker frontend build uses `npm ci` (strict lockfile install) for reproducibility. Host development uses `npm install` (resolves to current lockfile). Never run `npm install` inside the Docker builder — it breaks reproducibility.

---

## Switching embedding model (Jina ↔ BGE-M3)

Model selection is env-driven. Edit `.env`:
```env
EMBEDDING_MODEL=bge-m3
RERANKER_MODEL=bge-reranker-base
```
Then recreate the containers + re-ingest:
```bash
docker compose up -d --force-recreate backend api-worker
```
Both models produce 1024-dim vectors (Jina uses Matryoshka truncation), so the Neo4j vector indexes don't change. Re-ingest documents to regenerate vectors with the new model.

---

## Documentation

- [`docker/README.md`](docker/README.md) — Docker build & run details (Linux + Windows Docker Desktop, GPU + WSL2)
- [`upload/v1.3-powershell-commands.md`](upload/v1.3-powershell-commands.md) — Windows PowerShell command runbook + Neo4j Browser usage
- [`upload/v1.3-embedding-migration.md`](upload/v1.3-embedding-migration.md) — Guide for adding a new embedding model (4 code locations)
- [`upload/v1.3-docker-design-decision.md`](upload/v1.3-docker-design-decision.md) — ADR: multi-stage + BuildKit cache architecture
- [`upload/z.ai-changes-v1.2.md`](upload/z.ai-changes-v1.2.md) — v1.2 pivot (sandbox → FastAPI + Neo4j)

---

## v1 Scope

Standard paths only: LongText + ChildChunk (Recursive/Semantic/Structure-Aware) ingest, hybrid search (vector + BM25 + adaptive α/β + optional reranker), Memory + MemoryCart, full observability. No Late/Agentic Chunking, no Structured Chat, no GraphRAG, no multi-user.
