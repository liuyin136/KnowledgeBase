# ADR-002: Vault Neo4j purge API selection

## Status

Accepted

## Date

2026-07-12

## Context

Neo4j purge functions evolved across Phase 1 flat ingest, v1.6 hierarchical tree, and v1.62 4-tier cutover. Multiple `delete_*` methods coexist in `Neo4jClient`. Using the wrong one leaves orphan nodes (vault empty but graph retains 70+ nodes per file) while SQLite delete succeeds silently.

Phase 1.63 confirmed root cause: `delete_file` called `delete_knowledge_by_source`, which only removes legacy `Knowledge` + `KnowledgeChunk`, not the v1.62 tree.

## Decision

All vault index lifecycle purges **must** go through `delete_ingestion_tree_for_source(source_file)`.

Call sites: `vault_store._purge_neo4j_ingestion()`, clear-index, sync drift purge, migration scripts.

## delete_* matrix

| Function | Scope | Use when |
|----------|-------|----------|
| `delete_ingestion_tree_for_source` | v1.62 tree + legacy `KnowledgeChunk` + `Knowledge` + `LogFile` | **Vault delete (indexed), clear index, sync drift, per-file migration** |
| `delete_knowledge_tree_for_source` | v1.62 tree only (family → grandchild) | Internal; called by `delete_ingestion_tree_for_source` |
| `delete_legacy_chunks_for_source` | Flat `KnowledgeChunk` via `HAS_CHUNK` | Internal; called by `delete_ingestion_tree_for_source` |
| `delete_knowledge_by_source` | Legacy `Knowledge` + `KnowledgeChunk` only | **Do not use for vault lifecycle** |
| `delete_knowledge_by_prefix` | Legacy knowledge under path prefix | Folder-level legacy cleanup; migration scripts |
| `delete_all_vault_ingestion` | All known vault `source_file` values + `_benchmark/` | `vault_reset_to_not_indexed.py`, migration |
| `delete_all_ingestion` | Global wipe of all ingestion labels | Destructive reconstruct only |
| `delete_all_knowledge` | Deprecated wrapper | Prefer `delete_all_ingestion` |

Implementation: `backend/app/services/neo4j_client.py` (lines ~280–470).

Vault wiring: `backend/app/services/vault_store.py` → `_purge_neo4j_ingestion()`.

## Alternatives considered

### Delete only the tier that failed

Rejected: orphan risk; full tree purge per `source_file` is cheap and idempotent.

### Keep `delete_knowledge_by_source` as default for simplicity

Rejected: proven to leave v1.62 nodes; caused production data drift.

## Consequences

- Neo4j purge failures must be logged (`logger.warning("neo4j_purge_failed", ...)`) — never silent `except: pass`
- Regression tests assert correct purge function: `tests/test_vault_batch.py`, `tests/test_neo4j_ingestion_purge.py`
- `not_indexed` file delete skips Neo4j purge (see ADR-003)

## Wrong patterns

```python
# WRONG — leaves v1.62 tree nodes
client.delete_knowledge_by_source(relative_path)

# CORRECT
client.delete_ingestion_tree_for_source(relative_path)
```

- Purging Neo4j when deleting a `not_indexed` file (no index exists)
- Using `delete_all_ingestion` for single-file delete
- Assuming SQLite delete implies Neo4j purge happened
