# KnowledgeBase3 — Agent Bootstrap

Personal RAG platform on Docker (Neo4j + Redis + FastAPI + GPU worker + Next.js).

**Current baseline:** Phase 2.01 extraction model prep SHIP. Next: Phase 2.02 question subgraph PLAN/BUILD.

---

## Read order

1. This file (`AGENTS.md`)
2. [tasks/PHASE_STATUS.md](tasks/PHASE_STATUS.md) — what's done / what's next
3. **Phase 1.x:** [Download/RAG Workflow template/HybridSearchAndFusionEngine_v1.51.md](Download/RAG%20Workflow%20template/HybridSearchAndFusionEngine_v1.51.md) — hybrid search canon  
   **Phase 2+ GraphRAG:** [Download/RAG Workflow template/GraphRAG_v2_Master_Index.md](Download/RAG%20Workflow%20template/GraphRAG_v2_Master_Index.md) — GraphRAG v2 canon
4. Relevant [tasks/CP-*-E2E.md](tasks/) checklist for the phase you touch
5. Template plan for the active phase (e.g. `plan-phase-2.01.md`)
6. **Trap log** for active phase: [docs/pitfalls/](docs/pitfalls/) — grep before BUILD/DEBUG steps

**Conflict rule:** `Download/RAG Workflow template/` wins over `.cursor/plans/RAG/` on scope and requirements. Cursor plans are execution logs, not specs.

**ADRs (schema / purge / status):** [docs/decisions/](docs/decisions/)

**Incidents (closed bugs, grep before re-debug):** [docs/incidents/](docs/incidents/)

**Traps (BUILD dead ends, grep before steps):** [docs/pitfalls/](docs/pitfalls/)

**Developer Cursor guide:** [docs/user-guide/how-you-use-cursor.md](docs/user-guide/how-you-use-cursor.md)

---

## Services and URLs

| Service | Container | Port | Role |
|---------|-----------|------|------|
| Backend API | `raglab-backend` | 8000 | FastAPI gateway (CPU) |
| GPU worker | `raglab-api-worker` | — | RQ jobs: ingest, search, embed |
| Frontend | `raglab-frontend` | 3000 | Next.js `/rag` UI |
| Neo4j | `raglab-neo4j` | 7474 / 7687 | Vector + BM25 + graph |
| Redis | `raglab-redis` | 6379 | RQ queue + cache |

```bash
docker compose up -d
curl http://localhost:8000/health
# UI: http://localhost:3000/rag
```

Shell into containers:

```bash
docker exec -it raglab-backend bash
docker exec -it raglab-api-worker bash
docker exec -it raglab-redis redis-cli
```

---

## Volume mounts and reload discipline

From [docker/docker-compose.yml](docker/docker-compose.yml):

| Service | Mounted | Rebuild needed? |
|---------|---------|-----------------|
| `backend` | `backend/app` | No — restart |
| `api-worker` | `backend/app`, `backend/scripts`, `tests` | No — restart |
| `frontend` | *(not mounted)* | **Yes** — `docker compose build frontend` |

**App-only changes:**

```bash
docker compose restart backend api-worker
```

**If HTTP/API behavior disagrees with mounted code** (stale uvicorn):

```bash
docker compose up -d --force-recreate backend
```

See [.cursor/rules/docker-build.mdc](.cursor/rules/docker-build.mdc) for full build vs restart rules.

---

## Test discipline

- pytest runs in **api-worker**, not `backend`
- Set `IN_WORKER_EXEC=1` for worker-context tests
- `backend` image does not include pytest

**Phase 1.7 regression gate:**

```bash
docker compose exec -e IN_WORKER_EXEC=1 api-worker python -m pytest \
  tests/test_vault_api.py \
  tests/test_vault_upload_upsert.py \
  tests/test_vault_batch.py \
  tests/test_ingest_estimate.py \
  tests/test_vault_clear_index.py \
  tests/test_vault_batch_ingest.py \
  tests/test_vault_list_content_search.py \
  tests/test_vault_scoped_search.py -q
```

**Original Phase 1 gate** (chunking, fusion, search schemas):

```bash
docker compose exec -e IN_WORKER_EXEC=1 api-worker python -m pytest \
  tests/test_chunking.py tests/test_fusion.py tests/test_hybrid_benchmark.py \
  tests/test_search_schemas.py tests/test_hybrid_integration.py -q
```

`test_hybrid_integration.py` may skip on CUDA OOM — that is expected when VRAM is exhausted.

---

## Neo4j purge rule

Vault index lifecycle **must** use `delete_ingestion_tree_for_source` — never `delete_knowledge_by_source` alone.

See [ADR-002](docs/decisions/ADR-002-vault-neo4j-purge-api.md).

Implementation: `backend/app/services/vault_store.py` → `_purge_neo4j_ingestion()`.

---

## VRAM and worker crashes

| Symptom | Likely cause |
|---------|--------------|
| `ggml_cuda_error`, signal 6 (SIGABRT) | GPU VRAM exhausted |
| `Work-horse terminated unexpectedly; waitpid returned 134` | Same — worker crash during embed/rerank |

Constraints: RTX 3070 Ti, ≤ 7 GB VRAM peak, `WORKER_CONCURRENCY=1`, single model slot in `jina_runtime`.

**Not** API routing, Neo4j, or frontend bugs until GPU path is ruled out.

---

## Key code paths

| Area | Path |
|------|------|
| Ingest + search workers | `backend/app/workers/tasks.py` |
| Neo4j client | `backend/app/services/neo4j_client.py` |
| Vault filesystem + purge | `backend/app/services/vault_store.py` |
| Vault SQLite | `backend/app/services/vault_db.py` |
| Search scope / allowlist | `backend/app/services/vault_scope.py` |
| Chunking / fusion | `backend/app/services/chunking.py`, `fusion.py` |
| RAG UI | `src/app/rag/`, `src/components/rag/` |
| Vault API client | `src/lib/api/vault.ts` |

---

## Scripts catalog

| Script | When to use |
|--------|-------------|
| `scripts/agent_smoke.py` | Pre-BUILD/DEBUG: health, imports, vault DB |
| `scripts/read-only/init_neo4j.py` | Schema init (first deploy) |
| `scripts/vault_reset_to_not_indexed.py` | Phase 1.7 one-time: purge Neo4j, mark all `not_indexed` |
| `scripts/vault_reset_and_reindex.py` | Destructive v1.62 reconstruct (disk + Neo4j + reindex) |

```bash
docker compose run --rm api-worker python scripts/agent_smoke.py
docker compose run --rm api-worker python scripts/vault_reset_to_not_indexed.py --dry-run
```

---

## After BUILD / DEBUG (SHIP checklist)

1. Run pytest gate from [PHASE_STATUS.md](tasks/PHASE_STATUS.md) or active plan Skill Exit.
2. Developer signs **Outcome Gates** (Then only) in active `tasks/CP-*-E2E.md`.
3. Update [PHASE_STATUS.md](tasks/PHASE_STATUS.md): Status + Changelog one line.

### Skill Exit — TRAPS (mandatory on BUILD)

Every **BUILD step** in the active plan:

1. **Start:** grep [docs/pitfalls/](docs/pitfalls/) (active `TRAPS-PHASE-*.md` + [TRAPS-GLOBAL.md](docs/pitfalls/TRAPS-GLOBAL.md)) for step keywords.
2. **End:** if the step hit a non-obvious wrong path (dead end, misleading error, spec mismatch) → **append one entry** to the phase trap file ([_TEMPLATE.md](docs/pitfalls/_TEMPLATE.md)). Skip only if the lesson is already in ADR/INC (see pitfalls [README](docs/pitfalls/README.md)).
3. **Escalate:** confirmed bug → DEBUG → INC; invariant policy → `adr_candidate: true` → ADR.

Plans must include this row in **Skill Exit** (see [IMPLEMENTATION_PLAN.md](tasks/templates/IMPLEMENTATION_PLAN.md)).

DEBUG: create `.cursor/debug-session.active` at start. Grep traps before incidents. On confirmed root cause, write `.cursor/debug-pending.json` → stop hook drafts `docs/incidents/INC-DRAFT-*.md` and (if `adr_candidate: true`) `docs/decisions/ADR-NNN-*.md`. Missing JSON with active session → hook warns stdout. See [docs/user-guide/how-you-use-cursor.md](docs/user-guide/how-you-use-cursor.md).

---

## Active plan pointer

BUILD reads only [tasks/plan.md](tasks/plan.md) → linked `.cursor/plans/*.plan.md`. Template: [tasks/templates/IMPLEMENTATION_PLAN.md](tasks/templates/IMPLEMENTATION_PLAN.md).

---

## Agent skills

Route via [.cursor/rules/agent-rule.mdc](.cursor/rules/agent-rule.mdc).


---

## Locked stack summary

- **Storage:** Neo4j 5.20 (HNSW 256d + 512d + BM25)
- **Embed:** Jina v5-omni-retrieval GGUF
- **Chunking:** v1.62 4-tier (Family → Parent → Child → Grandchild); grandchild embedded
- **Fusion:** Z-score w1=0.7 vector + w2=0.3 BM25; cascade W1–W5 hierarchical
- **Ingest:** Manual (1.7) — upload stores only; explicit ingest with token estimate
- **Search:** Indexed-only by default; vault-scoped filters (1.5)
- **Memory:** Manual only (Phase 2, not started)
