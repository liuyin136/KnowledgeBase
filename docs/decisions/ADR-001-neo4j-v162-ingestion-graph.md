# ADR-001: Neo4j v1.62 ingestion graph

## Status

Accepted

## Date

2026-07-12

## Context

Phase 1 began with flat ingest: `:Knowledge` + `:KnowledgeChunk` with `HAS_CHUNK`. Phase 1.6 introduced hierarchical chunking; Phase 1.62 hard-cutover replaced it with a 4-tier graph. Search, fusion, and future memory features must target the active graph, not legacy flat chunks.

Key requirements:

- Small-to-big retrieval: search at fine granularity, return parent context
- All tiers embedded (Matryoshka 256d / 512d coarse + 1024d stored)
- Front-matter stripped before chunking; stored in SQLite `vault_doc_meta`, not embedded
- Cascade fusion W1 (highest) through W5 (lowest) by tier

## Decision

Use the v1.62 4-tier Neo4j ingestion graph as the **only** active ingest/search model for vault content.

### Labels and relationships

```
Knowledge (root per source_file)
  ├─[:HAS_FAMILY]─> Knowledgechunk_family
  │                  └─[:HAS_SECTION]─> Knowledgechunk (parent / section)
  └─[:HAS_SECTION]─> Knowledgechunk (parent, when no family)
                       └─[:HAS_CHILD]─> Knowledgechunk_sen (child / paragraph)
                                          └─[:HAS_GRANDCHILD]─> Knowledgechunk_grand (embedded / search tier)
```

| Label | Role | Embedded |
|-------|------|----------|
| `Knowledge` | Document root; `source_file` = vault `relative_path` | No |
| `Knowledgechunk_family` | AST-level family grouping | Yes |
| `Knowledgechunk` | Parent / section | Yes |
| `Knowledgechunk_sen` | Child / paragraph | Yes |
| `Knowledgechunk_grand` | Grandchild / sentence | **Yes — primary search tier** |

### Legacy (Phase 1 flat)

| Label | Role |
|-------|------|
| `KnowledgeChunk` | Flat token windows via `HAS_CHUNK` |

Legacy nodes may coexist until purge but are **not** the active search path after v1.62 reconstruct.

## Alternatives considered

### Keep v1.6 3-tier only

Rejected: v1.62 adds family tier, structure-aware chunking, and cascade W1–W5 fusion with front-matter in SQLite.

### Dual-write flat + hierarchical

Rejected: doubles embed cost and complicates purge; hard cutover chosen instead.

## Consequences

- Full vault reconstruct required after v1.62 deploy (`vault_reset_and_reindex.py` or migrate flow)
- Phase 2 memory must link to `Knowledgechunk_grand` (or trace up), not flat `KnowledgeChunk` alone
- Schema DDL: `backend/scripts/init_schema.cypher`
- Models: `backend/app/models/neo4j_models.py`
- Ingest/search: `backend/app/workers/tasks.py`, `backend/app/services/hierarchical_fusion.py`

## Wrong patterns

- Assuming `:KnowledgeChunk` is the active hybrid search node
- Querying vector/BM25 indexes against flat chunks after v1.62 cutover
- Embedding YAML front-matter (belongs in SQLite `vault_doc_meta`)
- Wiring Phase 2 `:Memory` → `:KnowledgeChunk` without v1.62 alignment
