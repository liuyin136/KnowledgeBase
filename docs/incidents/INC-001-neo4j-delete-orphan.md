# INC-001 — Vault delete left Neo4j orphan nodes

## Status

closed

## Date

2026-07-12

## Symptom

Library file deleted from vault (SQLite + disk empty) but Neo4j retained 70+ ingestion nodes for the same `source_file`.

## Root cause

`delete_file` called `delete_knowledge_by_source`, which only removes legacy `Knowledge` + `KnowledgeChunk`, not the v1.62 tree (`Knowledgechunk_family` → `Knowledgechunk_grand`).

## Fix

`vault_store._purge_neo4j_ingestion()` now calls `delete_ingestion_tree_for_source`. Neo4j purge failures logged, not swallowed.

## Files touched

- `backend/app/services/vault_store.py`
- `tests/test_vault_batch.py`

## Regression

```bash
docker compose exec -e IN_WORKER_EXEC=1 api-worker python -m pytest \
  tests/test_vault_batch.py tests/test_neo4j_ingestion_purge.py -q
```

## ADR

[ADR-002](../decisions/ADR-002-vault-neo4j-purge-api.md) — Wrong patterns section.
