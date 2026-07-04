# Docker Stack — Local-First RAG Experimentation Platform v1.2

Reproducible one-command Docker stack: **FastAPI backend + Next.js frontend +
Neo4j 5.20 + Redis 7** with NVIDIA GPU passthrough. Targets Windows Server
deployment with an NVIDIA GeForce GTX 3070 Ti (8 GB VRAM) or similar consumer GPU.

> Follows `infrastructure-environment-spec_v1.1.md` exactly. The base-image
> choice (`-runtime-` instead of `-devel-`) is documented inline in
> `Dockerfile.backend`.

---

## 1. File map

```
docker/
├── Dockerfile.backend          # multi-stage: model-downloader → runtime
├── Dockerfile.frontend         # multi-stage: builder → runner (standalone)
├── docker-compose.yml          # neo4j + redis + backend + api-worker + frontend
├── .env.example                # all env vars (infra spec §5)
└── README.md                   # this file

# At the project root:
docker-compose.yml              # thin wrapper: `include: [docker/docker-compose.yml]`
.dockerignore                   # root build context ignore
backend/.dockerignore           # backend build context ignore
```

---

## 2. Host prerequisites

### 2.1 Linux / WSL2 (recommended for development)

1. **Docker Engine 24+** with **BuildKit** (default since 23.0).
2. **NVIDIA Driver 535+** (`nvidia-smi` must work on the host).
3. **NVIDIA Container Toolkit** — install per
   <https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html>:
   ```bash
   # Ubuntu/Debian
   curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
     | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
   curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
     | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
     | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
   sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
   sudo nvidia-ctk runtime configure --runtime=docker
   sudo systemctl restart docker
   ```
4. Verify:
   ```bash
   docker run --rm --gpus all nvidia/cuda:12.4.1-runtime-ubuntu22.04 nvidia-smi
   ```

### 2.2 Windows Server (production target)

The stack runs **Linux containers** on Windows Server via one of two paths:

| Path | When to use | Notes |
|---|---|---|
| **Docker Desktop + WSL2 backend** | Single-server / dev | Easiest. Install Docker Desktop, enable WSL2 integration, then install NVIDIA Container Toolkit inside the default WSL2 distro (`wsl --install -d Ubuntu`). The Windows NVIDIA driver is shared. |
| **Docker EE (Mirantis Container Runtime) on Windows Server 2019/2022** | Production, no Desktop license | Use `Install-Module DockerMsftProvider -Force` then `Install-Package Docker -ProviderName DockerMsftProvider`. Linux containers run via LCOW or a Hyper-V Linux VM. GPU passthrough requires a Hyper-V Linux VM with PCI passthrough for the GPU — **Docker EE on Windows Server does NOT support `--gpus all` natively**. |

> **Recommended for Windows Server**: run Docker Engine inside a **WSL2 Ubuntu
> distro** (or a small Ubuntu VM with PCI passthrough). This gives you the
> same `--gpus all` workflow as native Linux. The `deploy.resources.reservations.devices`
> stanza in `docker-compose.yml` is honored by Docker Compose v2 on Linux/WSL2.

**NVIDIA driver on Windows Server**: install the latest Game Ready or Data
Center driver from <https://www.nvidia.com/Download/index.aspx>. The driver
must match the CUDA version — CUDA 12.4 needs driver **>= 550.54.14** (Linux)
or **>= 551.61** (Windows). The `nvidia/cuda:12.4.1-runtime-ubuntu22.04` image
ships the CUDA userspace libs; the kernel driver comes from the host.

---

## 3. One-command setup

From the project root (`/home/z/my-project` on the dev box):

```bash
# 0. (optional) copy env defaults
cp docker/.env.example docker/.env

# 1. Build all images (backend multi-stage pulls BGE-M3 + bge-reranker-base)
docker compose -f docker/docker-compose.yml build
#   — or —
docker compose build                       # uses the thin root wrapper

# 2. Download models (one-time; only needed if you skipped the build-time
#    download or want to refresh). The Dockerfile already bakes them in, so
#    this step is OPTIONAL unless you want to update models without rebuilding.
docker compose -f docker/docker-compose.yml run --rm backend python scripts/download_models.py

# 3. Initialize Neo4j indexes + constraints (one-time, idempotent)
docker compose -f docker/docker-compose.yml run --rm backend python scripts/init_neo4j.py

# 4. Start everything
docker compose -f docker/docker-compose.yml up -d

# 5. Verify
docker compose -f docker/docker-compose.yml ps
curl -s http://localhost:8000/health        # → {"status":"ok",...}
curl -s http://localhost:3000/api/v1/neo4j/health
# Neo4j browser: http://localhost:7474  (neo4j / P@ssw0rd)
```

> The thin root `docker-compose.yml` uses `include: [docker/docker-compose.yml]`,
> so `docker compose <cmd>` (no `-f`) works from the project root and is the
> recommended form for everyday use.

---

## 4. Service overview

| Service | Image / build | Ports | GPU | Health |
|---|---|---|---|---|
| `neo4j` | `neo4j:5.20-community` + APOC | 7474, 7687 | — | `GET /` on 7474 |
| `redis` | `redis:7-alpine` | 6379 | — | `redis-cli ping` |
| `backend` | build `../backend` → `Dockerfile.backend` | 8000 | ✅ | `GET /health` |
| `api-worker` | same image as backend, `command: python -m app.workers.worker` | — | ✅ | (none — long-running) |
| `frontend` | build `..` → `Dockerfile.frontend` | 3000 | — | (Next.js standalone) |

**GPU passthrough** is declared on `backend` and `api-worker` via:

```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: 1
          capabilities: [gpu]
```

Compose v2 + NVIDIA Container Toolkit translates this to `--gpus all`. On a
host without an NVIDIA GPU, **the backend + api-worker services will fail to
start** — either remove the `deploy.resources` stanza (CPU-only mode, slow) or
run on a GPU box.

---

## 5. Environment variables

See `.env.example` for the full list. The compose file already bakes in the
correct in-network values (`NEO4J_URI=bolt://neo4j:7687`, etc.). Override
only what you need via `docker/.env` or `export` before `docker compose up`.

Key ones:

| Var | Default | Notes |
|---|---|---|
| `NEO4J_PASSWORD` | `P@ssw0rd` | Change for any non-local deployment. |
| `CUDA_VISIBLE_DEVICES` | `0` | Set to `all` for multi-GPU; `-1` to disable GPU. |
| `DOWNLOAD_RERANKER` | `1` | Build-time. `0` skips `BAAI/bge-reranker-base` (~1 GB smaller). |
| `LOG_LEVEL` | `INFO` | `DEBUG` for verbose logs. |
| `BACKEND_URL` | `http://backend:8000` | Used by the Next.js server for SSR fetches. |
| `NEXT_PUBLIC_BACKEND_URL` | (empty) | **Leave empty** — frontend proxies via same-origin `/api/v1/*`. |

---

## 6. Multi-stage build rationale

### `Dockerfile.backend`
- **Stage 1 `model-downloader`** (`python:3.12-slim`): installs `huggingface_hub`
  + `git-lfs` and snapshots `BAAI/bge-m3` + `BAAI/bge-reranker-base` into
  `/app/models/<name>/`. Uses a BuildKit cache mount on `/root/.cache/huggingface`
  so rebuilds don't re-download the ~2.4 GB of weights.
- **Stage 2 `runtime`** (`nvidia/cuda:12.4.1-runtime-ubuntu22.04`): installs
  Python 3.12 from deadsnakes + minimal system deps, copies models from stage 1,
  copies backend code, installs `requirements.txt` with `--no-cache-dir`.
  Final CMD: `uvicorn app.main:app --host 0.0.0.0 --port 8000`.

### `Dockerfile.frontend`
- **Stage 1 `builder`** (`node:22-alpine` + bun): `bun install --frozen-lockfile`,
  `bun run build` (standalone output — `next.config.ts` has `output: "standalone"`
  verified at build time).
- **Stage 2 `runner`** (`node:22-alpine`): copies `.next/standalone` +
  `.next/static` + `public/`, runs `node server.js` as non-root. Final image
  ~150 MB.

---

## 7. Troubleshooting

### CUDA not visible in the backend container
**Symptom**: `torch.cuda.is_available()` returns `False`, or `nvidia-smi: command not found`.

**Fix**:
1. Verify `nvidia-smi` works on the host.
2. Verify the NVIDIA Container Toolkit is installed:
   ```bash
   nvidia-ctk --version
   docker info | grep -i runtime   # should list 'nvidia'
   ```
3. Test the runtime directly:
   ```bash
   docker run --rm --gpus all nvidia/cuda:12.4.1-runtime-ubuntu22.04 nvidia-smi
   ```
4. If step 3 fails on **Windows Server / Docker EE**, GPU passthrough is NOT
   supported in LCOW. Move the stack to a WSL2 Ubuntu distro or a Hyper-V
   Linux VM with GPU passthrough.
5. If running `docker compose` (not `docker run`), make sure Compose v2 is in
   use (`docker compose version` should show v2.x). Compose v1 ignores the
   `deploy.resources.reservations.devices` stanza.

### Neo4j auth error / `Neo.ClientError.Security.Unauthorized`
**Symptom**: Backend logs show `neo4j.exceptions.AuthError: The client is unauthorized`.

**Fix**:
- The password in `docker-compose.yml` is `P@ssw0rd` (per infra spec §3).
  If you changed it in `.env`, also delete the volume so Neo4j re-initializes:
  ```bash
  docker compose down
  docker volume rm docker_neo4j_data
  docker compose up -d neo4j
  ```
- Wait ~30s for Neo4j to come up before starting the backend (`depends_on:
  service_healthy` already enforces this).

### Model download failures
**Symptom**: `model-downloader` stage fails with `ConnectionError` or
`RepositoryNotFoundError` during `docker compose build`.

**Fix**:
- HuggingFace Hub is occasionally rate-limited. Re-run the build —
  the BuildKit cache mount on `/root/.cache/huggingface` resumes partial
  downloads.
- If you're behind a corporate proxy, set `HTTPS_PROXY` in the build args:
  ```bash
  docker compose build --build-arg HTTPS_PROXY=http://your-proxy:8080 backend
  ```
- To skip the reranker (saves ~1 GB + time): `DOWNLOAD_RERANKER=0 docker compose build backend`.
- To pre-download models manually and mount them, use a volume:
  ```bash
  docker compose run --rm -v /path/to/local/models:/app/models backend python scripts/download_models.py
  ```

### Port conflicts (7474 / 7687 / 6379 / 8000 / 3000)
**Symptom**: `bind: address already in use` on `docker compose up`.

**Fix**:
- Find what's holding the port: `sudo lsof -i :8000` (Linux) or
  `Get-NetTCPConnection -LocalPort 8000` (Windows PowerShell).
- Either stop the conflicting service or remap in `docker-compose.yml`:
  ```yaml
  ports:
    - "8001:8000"   # host:container
  ```
- On Windows Server, IIS commonly holds :80 / :443 but the RAG stack doesn't
  use those ports.

### `docker compose run` hangs on `--rm`
**Symptom**: `docker compose run --rm backend python scripts/init_neo4j.py`
hangs after the script exits.

**Fix**: This usually means the script didn't close the Neo4j driver. Add an
explicit `driver.close()` in `scripts/init_neo4j.py`, or kill the container
with `Ctrl-C` (the `--rm` flag still cleans it up).

### Frontend `502` / `Bad Gateway` on `/api/v1/*`
**Symptom**: Browser hits `localhost:3000/api/v1/...` and gets a 502.

**Fix**: The Next.js server proxies to `http://backend:8000`. Verify the
backend is healthy:
```bash
docker compose ps backend
docker compose logs backend | tail -50
curl -s http://localhost:8000/health
```
If the backend is restarting, check `docker compose logs backend` for Neo4j
or Redis connection errors (see the two items above).

### `next.config.* must set output: 'standalone'` build error
**Symptom**: Frontend build fails with the sanity-check from `Dockerfile.frontend`.

**Fix**: `next.config.ts` already has `output: "standalone"` (verified). If
you reverted it, re-add:
```ts
const nextConfig: NextConfig = {
  output: "standalone",
  // ...
};
```

---

## 8. Updating models

To update BGE-M3 or the reranker without rebuilding the whole stack:

```bash
# Re-download into a running backend container (writes to /app/models)
docker compose exec backend python scripts/download_models.py

# Or, re-run the build (BuildKit cache makes this fast if nothing changed)
docker compose build backend
docker compose up -d backend api-worker
```

---

## 9. Backups

```bash
# Neo4j full dump
docker compose exec neo4j neo4j-admin database dump --to-path=/data/dumps neo4j

# Redis (AOF is already enabled in compose; just snapshot the volume)
docker run --rm -v docker_redis_data:/data -v "$PWD":/backup alpine \
  tar czf /backup/redis-$(date +%F).tgz -C /data .

# Restore Neo4j
docker compose down neo4j
docker compose run --rm neo4j neo4j-admin database load --from-path=/data/dumps neo4j
docker compose up -d neo4j
```

---

## 10. Tear down

```bash
# Stop + remove containers, keep volumes
docker compose down

# Stop + remove containers AND volumes (DESTRUCTIVE — drops Neo4j + Redis data)
docker compose down -v
```
