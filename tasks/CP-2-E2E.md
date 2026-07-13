# CP-2 E2E Verification — GraphRAG + Memory

Manual checklist for Phase 2 exit gate: manual save from fusion hits → entity graph → community summaries → graph search → episodic/semantic memory.

**Developer:** sign **Outcome Gates** below only. Step-by-step flows are in the appendix for agents.

**Spec:** [plan-phase-2.md](../Download/RAG%20Workflow%20template/plan-phase-2.md)

---

## Outcome Gates (developer signs)


| ID  | Given                                    | When                                             | Then                                                                              | [ ] |
| --- | ---------------------------------------- | ------------------------------------------------ | --------------------------------------------------------------------------------- | --- |
| G1  | Indexed vault + successful `/rag/search` | User selects ≥2 grandchild hits and saves        | Neo4j shows Entity/Relation/Claim linked to `:Knowledgechunk_grand`               |     |
| G2  | G1 memory exists                         | Same query + same hit set saved again            | One `:Memory`, `version` incremented; no duplicate entities for same `memory_key` |     |
| G3  | G1 memory exists                         | `POST /graph/search` local mode with seed entity | Multi-hop paths + source grandchild IDs returned                                  |     |
| G4  | G1 memory exists                         | `POST /graph/search` global mode with query      | Community summaries + cross-entity paths returned                                 |     |
| G5  | G1 save completed                        | Load episodic session by `session_id`            | Redis record contains `retrieval_tree`, selected IDs, `memory_key`                |     |
| G6  | Search completes without save            | —                                                | No new `:Memory`/`:Entity` nodes; no extract job enqueued                         |     |
| G7  | Search then manual save in same worker   | —                                                | No GPU OOM; worker logs VRAM before/after Liquid                                  |     |
| G8  | `/rag/memory` UI                         | Select hits → confirm → poll job                 | Summary + entity count shown; Memory nav enabled                                  |     |


**Verify:**

```bash
docker compose exec -e IN_WORKER_EXEC=1 api-worker python -m pytest \
  tests/test_graph_memory_schema.py \
  tests/test_liquid_extract_parser.py \
  tests/test_memory_extract.py \
  tests/test_graph_community.py \
  tests/test_memory_episodic.py \
  tests/test_memory_api.py \
  tests/test_graph_search.py \
  tests/test_memory_vram.py -q
```

**Prereq regression (unchanged):**

```bash
docker compose exec -e IN_WORKER_EXEC=1 api-worker python -m pytest \
    \
  tests/test_ingest_estimate.py tests/test_vault_clear_index.py \
  tests/test_vault_batch_ingest.py tests/test_vault_list_content_search.py \
  tests/test_vault_scoped_search.py -q
```

---



## Sign-off

Mirror Outcome Gate IDs — check only when Then is true:

- [x] G1
- [x] G2
- [x] G3
- [x] G4
- [x] G5
- [x] G6
- [x] G7
- [x] G8

---



## Appendix — Agent flows (optional)

Step-by-step UI/API flows for agent verification. **Not required for developer sign-off.**

### Flow 1 — Search → save → Neo4j verify

> Sign **G1** in Outcome Gates instead.

1. Open `/rag/search`; run query against indexed content
2. Select ≥2 hits (note `grandchild_id` values)
3. Open `/rag/memory`; confirm selection
4. Click Save → confirm dialog → poll job to completion
5. Neo4j Browser: `MATCH (m:Memory)-[:RETRIEVED]->(g:Knowledgechunk_grand) RETURN m, g LIMIT 10`
6. Verify Entity/Relation/Claim nodes with `PROVENANCE` to grandchild

- [x] Extract job completes without error
- [x] Graph nodes visible for saved `memory_key`



### Flow 2 — LWW re-extract

> Sign **G2** instead.

1. Repeat Flow 1 with same query + same grandchild selection
2. Check `:Memory.version` incremented
3. Confirm single Memory node for `memory_key`

- [x] `version = 2` (or higher)
- [x] No duplicate Entity nodes for same names within batch



### Flow 3 — Graph local search

> Sign **G3** instead.

1. Pick `entity_id` from G1 graph
2. `POST /api/v1/graph/search` with `mode: local`, `hops: 2`
3. Inspect `paths` and `sources`

- [x] Response includes multi-hop path
- [x] `sources` list non-empty grandchild IDs



### Flow 4 — Graph global search

> Sign **G4** instead.

1. `POST /api/v1/graph/search` with `mode: global`, query related to saved content
2. Inspect `community_summaries`

- [x] At least one community summary returned
- [x] Scoped to saved `memory_key` when provided



### Flow 5 — No auto-extract on search-only

> Sign **G6** instead.

1. Run search; do **not** save
2. Count `:Memory` and `:Entity` nodes before/after (or check no extract job in Redis/RQ)

- [x] Node counts unchanged
- [x] No `extract_memory_graph` job enqueued



### Flow 6 — VRAM sequential search → extract

> Sign **G7** instead.

1. Run hybrid search job on worker
2. Immediately run manual extract on same worker process
3. Check worker logs for VRAM before/after Liquid

- [x] No SIGABRT / work-horse crash
- [x] VRAM log lines present