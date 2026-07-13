# Phase 1.61 — Vault Migration & Ingest Progress Patch

**Status:** Implemented  
**Plan:** `.cursor/plans/RAG/phase_1.61_vault_reindex_20260712.plan.md`

## Summary

One-shot full v1.6 vault migration (Neo4j complete purge → Redis cache clear → vault
status reset → enqueue all ingests) plus 5-phase ingest progress visible through job
completion.

## Patches

| Patch | Deliverable |
|-------|-------------|
| P1 | `delete_ingestion_tree_for_source`, `delete_all_vault_ingestion`, `delete_all_ingestion` in `neo4j_client.py` |
| P2 | `vault_migration.py` + rewritten `vault_reset_and_reindex.py` |
| P3 | Final ingest progress publish + `workflow_log` in job result; jobs API on `finished` |
| P4 | `POST /api/v1/rag/vault/migrate-v16` |
| P5 | Library **Migrate & Reindex All** + `VaultMigrateProgress` |
| P6 | Runbook path fixes + `scripts/init_neo4j.py` wrapper |
| P7 | `tasks/CP-1.61-E2E.md` + automated tests |

## QA

See `tasks/CP-1.61-E2E.md` and `backend/scripts/migrate_v16_reindex.md`.
