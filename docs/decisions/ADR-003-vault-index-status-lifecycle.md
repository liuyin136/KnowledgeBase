# ADR-003: Vault index status lifecycle (Phase 1.7)

## Status

Accepted

## Date

2026-07-12

## Context

Before Phase 1.7, upload and save auto-enqueued ingest, coupling library file storage to GPU/Neo4j load. Phase 1.7 decouples storage from indexing: users upload first, ingest explicitly with token estimate confirmation. Search must remain indexed-only.

Statuses live in SQLite `vault_files.index_status` and drive UI badges, purge behavior, and search allowlists.

## Decision

### Status enum

Defined in `backend/app/models/vault_schemas.py`:

| Status | Meaning |
|--------|---------|
| `not_indexed` | File on disk; no Neo4j index (default after upload/create) |
| `pending` | Ingest job running (`ingest_lock_job_id` set) |
| `indexed` | Neo4j v1.62 tree exists |
| `error` | Last ingest failed |
| `modified` | Legacy; UI deprecated — indexed save auto-reingests instead |
| `deleted` | Soft-deleted row (excluded from lists) |

### State machine

```
not_indexed ──[user ingest]──> pending ──[success]──> indexed
                                  └──[fail]──> error

indexed ──[user save edit]──> auto re-ingest ──> pending ──> indexed

indexed ──[clear index]──> not_indexed  (Neo4j purged, file kept)

any active ──[delete]──> deleted
  Neo4j purge when status in (indexed, error, modified)
  no Neo4j purge when not_indexed
```

### Lifecycle rules

| Action | `not_indexed` | `indexed` |
|--------|---------------|-----------|
| Upload / create | Store disk + SQLite only | — |
| Save | Store only | Store + auto re-ingest |
| Ingest | User-initiated (single or bulk) with token preview | N/A (already indexed) |
| Clear index | 409 error | Purge Neo4j → `not_indexed` |
| Delete | Disk + SQLite only | Disk + SQLite + Neo4j purge (ADR-002) |
| Search | Excluded (`indexed_only=true` default) | Included when in scope |

Purge gate: `vault_store._should_purge_neo4j_on_delete()` returns true for `indexed`, `error`, `modified`.

Search: `vault_scope.resolve_search_allowlist()` defaults `indexed_only=True`; empty allowlist returns explicit no-results path.

## Alternatives considered

### Keep auto-ingest on upload

Rejected: uncontrolled GPU load; user cannot preview token cost.

### Remove SQLite; disk-only metadata

Rejected: need folders, scope, status, locks, `doc_meta` for v1.62 front-matter.

## Consequences

- One-time deploy reset: `scripts/vault_reset_to_not_indexed.py` marks all files `not_indexed`
- Migrate flow no longer auto-reindexes; user runs bulk Ingest
- UI: `not_indexed` badge + bulk Ingest button; no `indexed_only=false` toggle on search
- Tests: `tests/test_vault_api.py`, `tests/test_vault_clear_index.py`, `tests/test_vault_batch_ingest.py`

## Wrong patterns

- Auto-enqueueing ingest on upload or `not_indexed` save
- Leaving `modified` status in UI after indexed save (should re-ingest immediately)
- Purging Neo4j when deleting `not_indexed` files
- Allowing search over `not_indexed` files in production UI
- Skipping token estimate in ingest confirm dialog
