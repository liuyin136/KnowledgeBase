# CP-1.5 — Vault-Scoped Search E2E Checklist

Manual verification after Phase 1.5 implementation. Run with stack up:

```bash
docker compose up -d
docker compose restart backend api-worker
docker compose build frontend
```

## Prerequisites

- [ ] Phase 1.4 vault has at least two folders with indexed files
- [ ] `/rag/search` loads without console errors

## Scoped search

- [ ] Open `/rag/search`
- [ ] Folder multi-select lists vault folders from API
- [ ] Select one folder only → search returns hits from that folder's files only
- [ ] Select two folders with different content → results include both scopes
- [ ] Set **Created after** / **Created before** → older files excluded
- [ ] Uncheck **Indexed files only** → allowlist includes `not_indexed` paths (may return fewer vector hits)
- [ ] Workflow log shows **Vault scope** step when filters active
- [ ] Footer shows allowlist path count when scoped

## Cache

- [ ] Repeat identical scoped query → **CACHED** indicator
- [ ] Change folder selection → cache miss (new job)

## Edge cases

- [ ] Scope with zero indexed files → empty results quickly (no long GPU wait)
- [ ] Over-broad scope (>500 files) → 422 with "narrow your filters" message

## Regression

- [ ] Unscoped search (no folders, no dates, indexed only checked) still searches full corpus
- [ ] `span_id` visible in footer
- [ ] Search hit cards show Open / Reindex / Delete when `file_id` present

## Sign-off

- [ ] CP-1.5C complete — ready for Phase 2
