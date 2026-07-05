# Task 7+8 (v1.3 docs) — ADRs + PowerShell runbook

Agent: full-stack-developer (v1.3 docs: ADRs + powershell)
Task ID: 7+8
Task: Write 3 v1.3 documentation files in `/upload`:
  1. `v1.3-embedding-migration.md` — Developer guide for adding a future embedding/reranker model (4 primary code locations + secondary locations + Jina v5 specifics + verification checklist).
  2. `v1.3-docker-design-decision.md` — ADR for the multi-stage + BuildKit cache architecture (context + decision + rationale + trade-offs + alternatives + verification checklist).
  3. `v1.3-powershell-commands.md` — Windows PowerShell entry-command runbook (prerequisites + one-time setup + start/stop/logs + service endpoints + Neo4j Browser usage + script execution + model switching + troubleshooting + verification checklist).

## Work Log

- Read `worklog.md` to load full project context (v1.1 sandbox → v1.2 FastAPI+Neo4j+Docker pivot → v1.3 Jina migration + Docker rectification). Reviewed the v1.2 change doc (`/upload/z.ai-changes-v1.2.md`).
- Read all referenced source files to ground the docs in actual code:
  - `docker/Dockerfile.backend` — confirmed the 2-stage build (Stage 1 `model-downloader` python:3.12-slim + BuildKit HF cache mount; Stage 2 `runtime` `nvidia/cuda:13.3.0-devel-ubuntu26.04` + Python 3.12 from apt + BuildKit pip cache mount + `PYTHONPATH=/app`).
  - `docker/docker-compose.yml` — confirmed 5 services (neo4j 5.20 + redis 7 + backend + api-worker + frontend), GPU reservations on backend + api-worker, `EMBEDDING_MODEL=jina-v5-small` + `RERANKER_MODEL=jina-v3` env vars, `EMBEDDING_DIM=1024` stable.
  - `backend/app/services/embedding.py` — confirmed the conditional `load()` branch (Jina: `trust_remote_code=True, truncate_dim=settings.embedding_dim`; BGE-M3: vanilla) + the conditional `embed_batch()` task branch (Jina: `task="retrieval.query"/"retrieval.passages"`; BGE-M3: ignored) + Construction note #1 float32 cast (`emb.detach().cpu().to(torch.float32)`) preserved on every encode path.
  - `backend/app/services/retrieval.py` — confirmed `_ensure_reranker()` conditional (Jina v3: `trust_remote_code=True`, max_length=8192; BGE-reranker-base: trust_remote=False, max_length=512) + `_rerank()` is model-agnostic (`CrossEncoder.predict()` works for all).
  - `backend/app/core/config.py` — confirmed the logical-id-based model selection (`EMBEDDING_MODEL_IDS`, `RERANKER_MODEL_IDS`, `MODEL_NATIVE_DIM` lookup tables) + derived properties (`embedding_repo`, `reranker_repo`, `model_dim`, `reranker_max_length`) + Pydantic validators.
  - `backend/scripts/download_models.py` — confirmed the Jina-default + optional BGE-via-`DOWNLOAD_BGE=1` download flow.
  - `backend/app/services/orchestrator.py` — confirmed the ChildChunk = LongText parent + child chunks pattern + the 4 embed call sites with `is_query` threading.
  - `src/lib/rag/types.ts` — confirmed the REST contract shape (SearchResult, SearchMetadata, SearchConfig, etc.).
  - `docker/.env.example` — confirmed `EMBEDDING_MODEL=jina-v5-small` + `RERANKER_MODEL=jina-v3` + `DOWNLOAD_BGE=0` defaults.
  - `backend/app/api/v1/dashboard.py` — confirmed the `system` block reports `embeddingModel` / `embeddingModelLogical` / `embeddingNativeDim` / `rerankerModel` / `rerankerModelLogical` / `rerankerMaxLength` dynamically from settings (no hardcoded model strings).
  - `backend/scripts/init_neo4j.py` — confirmed the idempotent schema initialization (constraints + vector indexes + fulltext) referenced by the PowerShell runbook.
- Reviewed prior agent context: `/agent-ctx/2-full-stack-developer-fastapi-backend.md`, `/agent-ctx/3-full-stack-developer-docker.md` (the v1.2 Docker baseline this ADR supersedes), `/agent-ctx/5-embedding-migration-full-stack-developer.md` (the v1.3 embedding migration this guide documents), `/agent-ctx/5-c-full-stack-developer.md`.
- **Wrote `/upload/v1.3-embedding-migration.md`** — Developer guide structured as: Overview → 4 primary code locations (config.py / embedding.py / retrieval.py / download_models.py + Dockerfile.backend model-download stage, each with file path + what-to-change + worked E5 example snippet) → Secondary locations (dashboard.py / settings-view.tsx / docker-compose.yml / .env.example / orchestrator.py / dashboard route.ts) → Jina v5 specifics (task conditioning, Matryoshka 1024, trust_remote_code, float32 cast) → 9-item verification checklist → cross-references. Construction note #1 float32 cast explicitly called out as MANDATORY for every model. Worked E5 example shows the "task prefix" pattern (different from Jina's "task kwarg" pattern) to demonstrate that the guide generalizes beyond Jina vs BGE.
- **Wrote `/upload/v1.3-docker-design-decision.md`** — ADR structured as: Context (host constraints + image size + v1.3 directive) → Decision (2-stage backend + 2-stage frontend + BuildKit cache mounts) → Rationale (6 bullets: why multi-stage / why BuildKit / why nvidia/cuda:13.3.0-devel-ubuntu26.04 / why python:3.12-slim for stage 1 / why standalone for frontend / why PYTHONPATH=/app) → Trade-offs table (5 pros + 3 cons) → Alternatives considered (6 rejected alternatives with reasons) → 10-item verification checklist → cross-references. Status: Accepted. Supersedes v1.2 single-stage + 12.4.1-runtime-ubuntu22.04 baseline.
- **Wrote `/upload/v1.3-powershell-commands.md`** — Windows runbook structured as: Prerequisites (Docker Desktop + WSL2 + NVIDIA Windows driver + NVIDIA Container Toolkit in WSL2 with the install commands) → One-time setup (Copy-Item .env, docker compose build, download_models.py, init_neo4j.py) → Start/stop/logs → Service endpoints table (6 services) → Neo4j Browser usage (5 Cypher query examples including the vector search with 1024-dim query vector placeholder + SHOW INDEXES) → Running .py files inside container (PYTHONPATH note + dev-only volume mount override) → Switching embedding model (5-step Jina↔BGE workflow with rebuild + recreate + re-ingest + verify) → Troubleshooting (6 common issues: GPU not visible / model download timeout / Neo4j auth / port conflict / CRLF errors / BuildKit not used — each with the exact PowerShell fix command) → 10-item verification checklist → cross-references. All commands in fenced ```powershell or ```bash blocks (WSL2 install commands are bash since they run inside the WSL2 Ubuntu shell, not PowerShell).
- Appended this work record to `/agent-ctx/7+8-full-stack-developer.md` AND to `/worklog.md` per the task's mandatory last step.

## Stage Summary

- 3 documentation files written to `/home/z/my-project/upload/`:
  - `v1.3-embedding-migration.md` — the developer guide for adding a future embedding/reranker model (4 primary code locations + worked E5 example + Jina v5 specifics + 9-item verification checklist).
  - `v1.3-docker-design-decision.md` — the ADR for the multi-stage + BuildKit cache architecture (status: Accepted; supersedes v1.2 baseline; 6-bullet rationale + trade-offs table + 6 rejected alternatives + 10-item verification checklist).
  - `v1.3-powershell-commands.md` — the Windows PowerShell runbook (prerequisites + WSL2 GPU setup + one-time setup + start/stop/logs + service endpoints + Neo4j Browser queries + script execution + model switching + 6 troubleshooting recipes + 10-item verification checklist).
- All docs are accurate to the actual code (verified by reading each referenced file before writing). No fabricated function signatures, env vars, or file paths.
- All 3 files include a verification checklist at the end (per the task spec).
- All PowerShell commands are in fenced ```powershell blocks (with ```bash only for the WSL2-internal NVIDIA Container Toolkit install, since those commands run inside the WSL2 Ubuntu shell, not PowerShell).
- Cross-references between the 3 docs + the existing v1.2 change doc + the v1.1 design specs are in place.
- No code changes were made — documentation only. No `bun run lint` or `python compileall` runs needed (no source files touched).
