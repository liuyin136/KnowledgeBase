# CP-1.7 E2E Verification — Manual Ingest Pipeline

Manual checklist for Phase 1.7 exit gate: upload without auto-ingest, explicit ingest with token preview, clear-index, delete by status, content search.

**Developer:** sign **Outcome Gates** below only. Step-by-step flows are in the appendix for agents.

---

## Outcome Gates (developer signs)

| ID | Given | When | Then | [ ] |
|----|-------|------|------|-----|
| G1 | Fresh upload of `.md` files | Upload completes | Files are `not_indexed`; search returns no hits for their content | [x] |
| G2 | Multiple `not_indexed` files selected | Bulk ingest with token confirm | Files become `indexed`; search returns their content | [x] |
| G3 | One `indexed` file | Clear index | File stays in library; status `not_indexed`; search has no hits | [x] |
| G4 | One `indexed` and one `not_indexed` file | Delete each | Indexed delete purges Neo4j; not_indexed delete skips Neo4j | [x] |
| G5 | Indexed file edited | Save | Auto re-ingest; search reflects updated content | [x] |
| G6 | Library folder with known body text | Content keyword filter | File appears without filename match | [x] |
| G7 | Scope with only unindexed files | Search on `/rag/search` | No spurious hits; indexed-only enforced in UI | [x] |

**Verify:**

```bash
docker compose exec -e IN_WORKER_EXEC=1 api-worker python -m pytest \
  tests/test_vault_api.py tests/test_vault_upload_upsert.py tests/test_vault_batch.py \
  tests/test_ingest_estimate.py tests/test_vault_clear_index.py \
  tests/test_vault_batch_ingest.py tests/test_vault_list_content_search.py \
  tests/test_vault_scoped_search.py -q
```

---

## Prerequisite — one-time deploy reset (production only)

After deploying 1.7 code, run once:

```bash
docker compose run --rm api-worker python scripts/vault_reset_to_not_indexed.py --dry-run
docker compose run --rm api-worker python scripts/vault_reset_to_not_indexed.py
docker compose restart backend api-worker
```

- [x] Dry-run prints source/file counts
- [x] Live run completes without error
- [x] All library files show `not_indexed` until ingested



## Flow 1 — Upload without ingest

> Appendix — agent reference. Sign **G1** in Outcome Gates instead.

1. Open `/rag/library`
2. Select a folder
3. Upload one or more `.md` files (drag-drop or browse)

- [x] Upload completes without ingest progress log in upload panel
- [x] Toast mentions files uploaded **(not indexed)**
- [x] Files appear with `not_indexed` status badge
- [x] Search for unique content from uploaded file returns **no hits** (until ingested)



## Flow 2 — Bulk ingest with confirmation

1. Select multiple `not_indexed` files
2. Click **Ingest selected**
3. Review confirm dialog (file count + estimated tokens)
4. Confirm

- [x] Confirm dialog shows token estimate and soft warning for large batches
- [x] Ingest progress modal shows workflow phases per file
- [x] Files transition to `indexed` when jobs complete
- [x] Search returns content from ingested files



## Flow 3 — Single-file ingest from row action

1. Pick a `not_indexed` file
2. Click **Ingest** on the row
3. Confirm in dialog

- [x] Ingest queues and completes
- [x] Status becomes `indexed`



## Flow 4 — Clear index (keep file)

1. Pick an **indexed** file
2. Click **Clear index** (row or bulk toolbar for selected indexed files)
3. Confirm

- [x] File remains in library and on disk
- [x] Status becomes `not_indexed`, chunk count 0
- [x] Search no longer returns that file's content
- [x] Clearing a `not_indexed` file returns error (409) if attempted via API



## Flow 5 — Delete by status

**Not indexed**

1. Delete a `not_indexed` file

- [x] Confirm copy mentions disk + metadata only (no Neo4j)
- [x] File removed from library

**Indexed**

1. Delete an **indexed** file

- [x] Confirm copy mentions Neo4j index removal
- [x] File removed; search no longer returns its chunks



## Flow 6 — Editor Save vs Ingest

**Not indexed file**

1. Open editor for `not_indexed` file
2. Edit and **Save**
3. Click **Ingest** and confirm

- [x] Save does not auto-ingest
- [x] Explicit Ingest builds index

**Indexed file**

1. Open editor for **indexed** file
2. Edit and **Save**

- [x] Save triggers auto re-ingest (progress modal)
- [x] File stays searchable with updated content



## Flow 7 — Library content keyword search

1. In library filter box, enter a phrase that appears in file **body** but not filename
2. Ensure folder scope contains the file

- [x] Matching file appears in list
- [x] Filename-only keywords still work
- [x] `relative_path` substring matches work



## Flow 8 — Search indexed-only

1. Open `/rag/search`
2. Confirm vault scope panel has **no** toggle to include unindexed files
3. Search with only `not_indexed` files in scope (or empty indexed scope)

- [x] Search does not expose `indexed_only=false` in UI
- [x] Empty indexed scope returns explicit no-results / scope message



## Flow 9 — Migrate without auto-reindex

1. Click **Migrate All** in library
2. Confirm destructive prompt

- [x] Migration completes without automatic ingest loop
- [x] Toast instructs to run bulk Ingest
- [x] Files are `not_indexed` after migration



## Automated regression

```bash
python -m pytest \
  tests/test_vault_api.py \
  tests/test_vault_upload_upsert.py \
  tests/test_vault_batch.py \
  tests/test_ingest_estimate.py \
  tests/test_vault_clear_index.py \
  tests/test_vault_batch_ingest.py \
  tests/test_vault_list_content_search.py \
  tests/test_vault_scoped_search.py -q
```



## Sign-off

Outcome Gates (primary):

- [x] G1 — upload without auto-ingest
- [x] G2 — manual ingest with token preview (single + bulk)
- [x] G3 — clear index keeps file, removes Neo4j
- [x] G4 — delete respects index status
- [x] G5 — indexed save auto-reingests
- [x] G6 — content keyword search
- [x] G7 — search indexed-only in UI