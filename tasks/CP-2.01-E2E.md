# CP-2.01 E2E Verification — Document Extraction Framework

Manual checklist for Phase 2.01: extraction model prep (P1–P3) then worker wiring (G1–G4).

**Developer:** sign **Outcome Gates** below only. Step-by-step flows are in the appendix for agents.

**Spec:** [plan-phase-2.01.md](../Download/RAG%20Workflow%20template/plan-phase-2.01.md)

---

## Prep Outcome Gates (extraction model — SHIP 2026-07-14)

| ID | Given | When | Then | [x] |
|----|-------|------|------|-----|
| P1 | — | `docker compose build api-worker && docker compose up -d api-worker` | Build succeeds; container healthy | x |
| P2 | api-worker running | `docker compose exec api-worker python /app/scripts/gliner2/gliner2-base-v1.py` | Prints `spaCy Entities:` and `GLiNER2 Entities:` | x |
| P3 | api-worker running + GPU | `docker compose exec api-worker python /app/scripts/Qwen/Qwen-8B.py` | Prints generated assistant text | x |

**Prep verify:**

```bash
docker compose exec -e IN_WORKER_EXEC=1 api-worker python -m pytest \
  tests/test_gliner_loader.py tests/test_qwen_loader.py tests/test_memory_vram.py -q
```

---

## Worker Outcome Gates (deferred — next slice)

| ID | Given | When | Then | [ ] |
|----|-------|------|------|-----|
| G1 | Indexed vault + grandchild content + query | Per-chunk extract (unit or worker) | Valid Pydantic JSON; at least one typed entity and one relationship with confidence | |
| G2 | Two chunks sharing an entity name | Merge step | Single merged entity node; duplicate relations collapsed | |
| G3 | Memory saved under 2.0 schema | Re-save same query + hit set after 2.01 deploy | `:Memory.version` incremented; Neo4j relations have `description` + `relation_type`; no new `:Claim` nodes | |
| G4 | Chunk text containing path with colons | Per-chunk extract | Parse succeeds (INC-004 regression) | |

**Verify:**

```bash
docker compose exec -e IN_WORKER_EXEC=1 api-worker python -m pytest \
  tests/test_liquid_extract_parser.py \
  tests/test_chunk_extract_framework.py \
  tests/test_memory_extract.py -q
```

**Prereq regression (Phase 2.0 ingest-side unchanged):**

```bash
docker compose exec -e IN_WORKER_EXEC=1 api-worker python -m pytest \
  tests/test_graph_memory_schema.py \
  tests/test_graph_community.py \
  tests/test_memory_api.py \
  tests/test_graph_search.py -q
```

---

## Sign-off

**Prep (SHIP 2026-07-14):**

- [x] P1
- [x] P2
- [x] P3

**Worker (next slice):**

- [ ] G1
- [ ] G2
- [ ] G3
- [ ] G4

---

## Appendix — Agent flows (optional)

### Flow 0 — Extraction model prep smoke

> Sign **P2** and **P3** instead.

1. `docker compose exec api-worker python /app/scripts/gliner2/gliner2-base-v1.py`
2. `docker compose exec api-worker python /app/scripts/Qwen/Qwen-8B.py`

### Flow 1 — Per-chunk extract smoke

> Sign **G1** instead.

1. Run blueprint script: `docker compose exec api-worker python /app/scripts/LiquidAI/lfm25-8b-a1b.py`
2. Run unit tests for `ChunkExtractResult` parser with fixture JSON

- [ ] JSON validates against Pydantic schema
- [ ] Entity types from closed catalog

### Flow 2 — Save with new extractor

> Sign **G3** instead.

1. `/rag/search` → select ≥2 hits → `/rag/memory` → Save
2. Neo4j: `MATCH (e:Entity {memory_key: $key}) RETURN e.name, e.description, e.type`
3. `MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) WHERE r.memory_key = $key RETURN r.relation_type, r.description, r.confidence`

- [ ] Entities have `description`
- [ ] Relations have `relation_type` and `confidence`
- [ ] No new Claim nodes after 2.01

### Flow 3 — LWW re-extract

> Part of **G3**.

1. Repeat save with same query + selection
2. Confirm `version >= 2` and single Memory per `memory_key`

- [ ] version incremented
- [ ] No duplicate entity names within batch

### Flow 4 — Colon path regression

> Sign **G4** instead.

1. Ingest chunk containing `.cursor/rules/docker-build.mdc):` text
2. Save to memory

- [ ] Job completes without `LiquidExtractError`
