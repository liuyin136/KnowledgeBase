# Active implementation plan (pointer)

> **Do not treat this file as the full plan.** It points to the current agent implementation plan. Project status: [PHASE_STATUS.md](PHASE_STATUS.md). Bootstrap: [AGENTS.md](../AGENTS.md).

| Field | Value |
|-------|-------|
| **Active plan** | [plan-phase-2.02.md](../Download/RAG%20Workflow%20template/plan-phase-2.02.md) |
| **Spec canon** | [Download/RAG Workflow template/plan-phase-2.02.md](../Download/RAG%20Workflow%20template/plan-phase-2.02.md) |
| **Outcome Gates** | [tasks/CP-2.02-E2E.md](CP-2.02-E2E.md) |
| **Phase** | 2.02 Question subgraph (next) |
| **Updated** | 2026-07-14 |
| **Checklist** | [tasks/todo.md](todo.md) |

## Completed (2026-07-14)

| Plan | Phase |
|------|-------|
| [phase_2.01_extraction_prep.plan.md](../.cursor/plans/RAG/phase_2.01_extraction_prep.plan.md) | 2.01 Extraction model prep (SHIP) |

## Rules

- **BUILD** reads only the plan linked above (via this pointer).
- `.cursor/plans/` files **without** a row here are archives — not active spec.
- Spec canon remains `Download/RAG Workflow template/` on conflict.
- **Step 1** in active plan is Docker/infra — developer runs `docker compose build api-worker` (not agent).

## Historical

| Plan | Phase |
|------|-------|
| [phase_2_graphrag_memory_20260712.plan.md](../.cursor/plans/RAG/phase_2_graphrag_memory_20260712.plan.md) | 2.0 GraphRAG + Memory (SHIP) |
| [phase_2_spec_rewrite_20260712.plan.md](../.cursor/plans/RAG/phase_2_spec_rewrite_20260712.plan.md) | DEFINE (spec + Outcome Gates design) |
