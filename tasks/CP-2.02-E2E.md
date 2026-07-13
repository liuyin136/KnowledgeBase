# CP-2.02 E2E Verification — Question Subgraph Extraction

Manual checklist for Phase 2.02 exit gate: question entities/keywords/intent → Neo4j question subgraph → traverser seeds.

**Developer:** sign **Outcome Gates** below only. Step-by-step flows are in the appendix for agents.

**Spec:** [plan-phase-2.02.md](../Download/RAG%20Workflow%20template/plan-phase-2.02.md)

---

## Outcome Gates (developer signs)

| ID | Given | When | Then | [ ] |
|----|-------|------|------|-----|
| G1 | 2.01 memory saved with search query | `extract_memory_graph` completes | Neo4j has `:QueryEntity` (or `Entity` with `origin=query`) linked to `:Memory` and `:UserQuery`; job reports `query_entities_created >= 1` | |
| G2 | G1 question subgraph exists | `POST /graph/search` local with seed from top QueryEntity | Non-empty `paths` and `sources` scoped to `memory_key` | |
| G3 | G1 memory + T2 stub API | `POST /memory/{memory_key}/question-extract` with follow-up question | New question nodes with `turn >= 1`; `GET .../question-graph` returns both turns | |

**Verify:**

```bash
docker compose exec -e IN_WORKER_EXEC=1 api-worker python -m pytest \
  tests/test_question_extract.py \
  tests/test_question_graph_neo4j.py -q
```

**Prereq (2.01 gate):**

```bash
docker compose exec -e IN_WORKER_EXEC=1 api-worker python -m pytest \
  tests/test_chunk_extract_framework.py -q
```

---

## Sign-off

Mirror Outcome Gate IDs — check only when Then is true:

- [ ] G1
- [ ] G2
- [ ] G3

---

## Appendix — Agent flows (optional)

### Flow 1 — Save-time question extract

> Sign **G1** instead.

1. Search with specific query (e.g. "What is MoE?")
2. Save ≥2 hits to memory
3. Neo4j: `MATCH (m:Memory)-[:SEEDED_BY]->(qe:QueryEntity) RETURN m.memory_key, qe.name, qe.role`

- [ ] QueryEntity nodes present
- [ ] `intent_summary` in job result or GET question-graph

### Flow 2 — Local graph search from query seed

> Sign **G2** instead.

1. `GET /api/v1/memory/{memory_key}/question-graph` → pick `query_entity_id`
2. `POST /api/v1/graph/search` `{ "mode": "local", "seed_entity_id": "...", "hops": 2, "memory_key": "..." }`

- [ ] `paths` non-empty
- [ ] `sources` contain grandchild_ids

### Flow 3 — Follow-up question (T2 stub)

> Sign **G3** instead.

1. `POST /api/v1/memory/{memory_key}/question-extract` with `{ "question_text": "Who uses it?", "turn": 1 }`
2. Poll job → `GET /api/v1/memory/{memory_key}/question-graph`

- [ ] `turn=1` QueryEntity or keyword nodes
- [ ] Original `turn=0` nodes retained
