# CP-1.5 — Vault-Scoped Search E2E Checklist

Manual verification after Phase 1.5 implementation. Run with stack up:

```bash
docker compose up -d
docker compose restart backend api-worker
docker compose build frontend
```

## Prerequisites

- [x] Phase 1.4 vault has at least two folders with indexed files
- [x] `/rag/search` loads without console errors

## Scoped search

- [x] Open `/rag/search`
- [x] Folder multi-select lists vault folders from API
- [x] Select one folder only → search returns hits from that folder's files only
- [x] Select two folders with different content → results include both scopes
- [x] Set **Created after** / **Created before** → older files excluded
- [x] Uncheck **Indexed files only** → allowlist includes `not_indexed` paths (may return fewer vector hits)
- [x] Workflow log shows **Vault scope** step when filters active
- [x] Footer shows allowlist path count when scoped



## Cache

- [x] Repeat identical scoped query → **CACHED** indicator
- [x] Change folder selection → cache miss (new job)



## Edge cases

- [x] Scope with zero indexed files → empty results quickly (no long GPU wait)
- [x] Over-broad scope (>500 files) → 422 with "narrow your filters" message



## Regression

- [x] Unscoped search (no folders, no dates, indexed only checked) still searches full corpus
- [x] `span_id` visible in footer
- [x] Search hit cards show Open / Reindex / Delete when `file_id` present



## Sign-off

- [x] CP-1.5C complete — ready for Phase 2