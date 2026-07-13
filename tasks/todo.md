# Phase 2 BUILD checklist

Active plan: [plan.md](plan.md) → [phase_2_graphrag_memory_20260712.plan.md](../.cursor/plans/RAG/phase_2_graphrag_memory_20260712.plan.md)

## Steps

- [x] **Step 0** — Spec canon sync (plan-phase-2, CP-2-E2E, master index)
- [x] **Step 1** — Infrastructure: `igraph` + `leidenalg`; `docker compose build api-worker`
- [x] **Step 2** — Neo4j graph-memory schema + client
- [x] **Step 3** — Liquid extraction module + parser tests
- [x] **Step 4** — `extract_memory_graph` worker + LWW → **CP-2A**
- [x] **Step 5** — Community detection + summaries → **CP-2B**
- [x] **Step 6** — Episodic Redis extension
- [x] **Step 7** — Memory API + job wiring
- [x] **Step 8** — Graph search API → **CP-2C**
- [x] **Step 9** — VRAM sequencing
- [x] **Step 10** — `/rag/memory` frontend → **CP-2D**
- [x] **Step 11** — SHIP: pytest gate + CP-2-E2E sign-off

## Checkpoints

- [x] CP-2A — Extract creates Entity/Relation/Claim + Memory + PROVENANCE
- [x] CP-2B — LWW re-extract; community + summary nodes
- [x] CP-2C — Graph search API; episodic session loadable
- [x] CP-2D — UI E2E; no OOM search→extract

## Outcome Gates (developer)

Sign in [CP-2-E2E.md](CP-2-E2E.md): G1–G8
