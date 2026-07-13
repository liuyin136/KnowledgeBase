# CP-1.63 E2E Verification — Post-1.62 Hotfixes

Manual checklist for Phase 1.63 exit gate (three post-deploy debug fixes).

## Flow 1 — Library folder create (orphan disk dir)

**Context:** After migrate/reconstruct, empty vault folder directories may remain on disk without SQLite rows.

1. Open `/rag/library`
2. In Folders panel, type a name matching an existing orphan disk folder (e.g. `News`, `Plan`)
3. Press **Add**

- [x] Folder is created with **201** (no Internal Server Error)
- [x] Folder appears in the folder list

## Flow 2 — Search after hierarchical fusion

1. Open `/rag/search`
2. Run a query against indexed content
3. Wait through workflow phases through `hierarchical_fusion`

- [x] No Internal Server Error during job polling
- [x] Rerank confirm dialog appears (`awaiting_rerank`)
- [x] Result cards show vector scores



## Flow 3 — Library file delete purges Neo4j

**Context:** Phase 1.62 indexes a 4-tier Neo4j tree per file. Legacy delete only removed `:KnowledgeChunk` nodes.

1. Open `/rag/library`
2. Pick an **indexed** file (note its path)
3. Delete the file (single or bulk delete)
4. Run a search for content unique to that file

- [x] File disappears from library list
- [x] Search no longer returns chunks from the deleted file
- [x] Optional Neo4j: `MATCH (n) WHERE n.source_file = '<path>' RETURN count(n)` → **0**



## Automated regression

```bash
docker compose run --rm api-worker pytest \
  tests/test_vault_api.py::test_create_folder_adopts_orphan_disk_dir \
  tests/test_jobs_search_finished.py \
  tests/test_vault_batch.py -q
```



## Sign-off

- [x] Orphan disk folder adopt works
- [x] Search job poll after fusion returns 200
- [x] Library delete removes v1.62 Neo4j ingestion nodes for that file