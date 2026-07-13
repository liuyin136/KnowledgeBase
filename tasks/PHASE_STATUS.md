# Phase Status

Living overview of RAG implementation progress. Update this file when a phase exits or verification evidence changes.

**Last updated:** 2026-07-14 — Phase 2.01 extraction model prep SHIP.

**Changelog:** Phase 2.01 prep SHIP — GLiNER2 + Qwen3-8B 4-bit stack live in api-worker; P1–P3 signed; `build-essential` in runtime image; Qwen stress script added.

---

## Status table

| Phase | Status | E2E / plan | Notes |
|-------|--------|------------|-------|
| Pre-phase | Done | [.cursor/plans/RAG/pre-phase_plan_remediation_20260711.plan.md](../.cursor/plans/RAG/pre-phase_plan_remediation_20260711.plan.md) | Docker/test discipline; template alignment |
| 1.0 CP-C | Done | [CP-C-E2E.md](CP-C-E2E.md) | Hybrid search MVP; `/rag` E2E |
| 1.4 Vault | Done | [plan-phase-1.4.md](../Download/RAG%20Workflow%20template/plan-phase-1.4.md) | SQLite on `vault_db_data` named volume |
| 1.5 Scoped search | Done | [CP-1.5-E2E.md](CP-1.5-E2E.md) | Folder + date filters on `/rag/search` |
| 1.51 Preview / upsert | Done | [phase_1.51_vault_preview_20260711.plan.md](../.cursor/plans/RAG/phase_1.51_vault_preview_20260711.plan.md) | Duplicate upload replace; library preview |
| 1.511 Rerank confirm | Done | [plan-phase-1.511.md](../Download/RAG%20Workflow%20template/plan-phase-1.511.md) | User confirm before rerank |
| 1.512 Live progress | Done | [plan-phase-1.512.md](../Download/RAG%20Workflow%20template/plan-phase-1.512.md) | Per-phase search job polling |
| 1.6 Hierarchical (v1.6) | Superseded | [plan-phase-1.6.md](../Download/RAG%20Workflow%20template/plan-phase-1.6.md) | Replaced by 1.62 hard cutover |
| 1.62 Hierarchical v2 | Done | [CP-1.62-E2E.md](CP-1.62-E2E.md) | 4-tier graph; cascade W1–W5; destructive reconstruct |
| 1.63 Hotfixes | Done | [CP-1.63-E2E.md](CP-1.63-E2E.md) | Folder create; job poll guard; Neo4j delete purge |
| **1.7 Manual ingest** | **Done (code + tests)** | [CP-1.7-E2E.md](CP-1.7-E2E.md) | Reset script run 2026-07-12; manual E2E sign-off optional |
| **2.0 GraphRAG + Memory** | **Done** | [plan-phase-2.md](../Download/RAG%20Workflow%20template/plan-phase-2.md) + [CP-2-E2E.md](CP-2-E2E.md) | Ingest-side graph store; extraction superseded by 2.01 at BUILD |
| **2.01 Extraction framework** | **Done (prep)** | [GraphRAG_v2_Master_Index.md](../Download/RAG%20Workflow%20template/GraphRAG_v2_Master_Index.md) + [plan-phase-2.01.md](../Download/RAG%20Workflow%20template/plan-phase-2.01.md) + [CP-2.01-E2E.md](CP-2.01-E2E.md) | GLiNER2 + Qwen3-8B 4-bit loaders SHIP; worker wiring (G1–G4) next |
| **2.02 Question subgraph** | **DEFINE done** | [plan-phase-2.02.md](../Download/RAG%20Workflow%20template/plan-phase-2.02.md) + [CP-2.02-E2E.md](CP-2.02-E2E.md) | QueryEntity seeds for traverser 2.1 |
| 2.1 Traverser | Not started | GraphRAG v2 index (planned) | Subgraph JSON |
| 2.2 Synthesizer | Not started | GraphRAG v2 index (planned) | LLM prompt package |
| 2.3 Answer LLM | Not started | GraphRAG v2 index (planned) | Thread + citations |
| 3.0 Observability | Not started | [plan-phase-3.md](../Download/RAG%20Workflow%20template/plan-phase-3.md) | VRAM guards, benchmarks, runbook |
| 4.0 PDF ingest | Not started | [plan-phase-4.md](../Download/RAG%20Workflow%20template/plan-phase-4.md) | |
| 5.0 Multimodal | Not started | [plan-phase-5.md](../Download/RAG%20Workflow%20template/plan-phase-5.md) | |

---

## Verification commands

### Phase 1.7 regression (required for vault/search changes)

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

### Phase 1.0 core (chunking, fusion, search API)

```bash
docker compose exec -e IN_WORKER_EXEC=1 api-worker python -m pytest \
  tests/test_chunking.py tests/test_fusion.py tests/test_hybrid_benchmark.py \
  tests/test_search_schemas.py tests/test_hybrid_integration.py -q
```

`test_hybrid_integration.py` may skip when CUDA VRAM is exhausted — acceptable during debug; run when GPU is idle before Phase 2 sign-off.

### Phase 2 GraphRAG + Memory (exit gate)

```bash
docker exec -e IN_WORKER_EXEC=1 raglab-api-worker python -m pytest \
  tests/test_graph_memory_schema.py \
  tests/test_liquid_extract_parser.py \
  tests/test_memory_extract.py \
  tests/test_graph_community.py \
  tests/test_memory_episodic.py \
  tests/test_memory_api.py \
  tests/test_graph_search.py \
  tests/test_memory_vram.py -q
```

**Evidence (2026-07-12):** 20 passed in 2.20s. `test_vault_scoped_search.py`: 3 passed. `test_vault_api.py` requires FastAPI (backend image only — not in api-worker).

### Phase 2.01 extraction prep (exit gate)

```bash
docker compose exec -e IN_WORKER_EXEC=1 api-worker python -m pytest \
  tests/test_gliner_loader.py \
  tests/test_qwen_loader.py \
  tests/test_memory_vram.py \
  tests/test_download_models2_extraction.py \
  tests/test_extract_llm.py -q
```

**Evidence (2026-07-14):** 7 passed in 4.34s. Prep smoke: `gliner2-base-v1.py`, `Qwen-8B.py` (models at `/app/models/GLiNER2`, `/app/models/Qwen3-8B`).

---

### Hierarchical / Neo4j purge (1.62 / 1.63)

```bash
docker compose exec -e IN_WORKER_EXEC=1 api-worker python -m pytest \
  tests/test_neo4j_v162_schema.py \
  tests/test_neo4j_ingestion_purge.py \
  tests/test_hierarchical_chunking_v162.py \
  tests/test_hierarchical_fusion.py -q
```

---

## Do not use as spec

[`.cursor/plans/RAG/`](../.cursor/plans/RAG/) — session-specific implementation and fix logs. On conflict with `Download/RAG Workflow template/`, **template wins**.

---

## Agent entry points

- [AGENTS.md](../AGENTS.md) — bootstrap (read first)
- [HybridSearchAndFusionEngine_v1.51.md](../Download/RAG%20Workflow%20template/HybridSearchAndFusionEngine_v1.51.md) — master index
- [docs/decisions/](../docs/decisions/) — ADR-001..005
- [docs/pitfalls/](../docs/pitfalls/) — TRAPS log (BUILD)
