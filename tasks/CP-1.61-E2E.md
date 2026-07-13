# CP-1.61 E2E Verification — Vault Migration & Ingest Progress

Manual browser checklist for Phase 1.61 exit gate. Run with stack up:

```bash
docker compose up -d
docker compose ps api-worker   # must be running for ingest jobs
```

## Prerequisites

- [x] `http://localhost:8000/health` returns OK
- [x] Phase 1.6 deployed (`api-worker` has `langchain-text-splitters` + spaCy)

## Flow 1 — Full CLI migration

1. Dry run:
  ```bash
   docker compose run --rm api-worker python scripts/vault_reset_and_reindex.py --dry-run
  ```
2. Live run:
  ```bash
   docker compose run --rm api-worker python scripts/vault_reset_and_reindex.py
  ```
3. Wait for all ingest jobs to finish (`docker compose logs -f api-worker`)
4. Neo4j checks:
  ```cypher
   MATCH (c:KnowledgeChunk) RETURN count(c);
   MATCH (p:Knowledgechunk) WHERE NOT (()-[:HAS_SECTION]->(p)) RETURN count(p);
  ```



## Flow 2 — Library Migrate & Reindex All

1. Open `http://localhost:3000/rag/library`
2. Click **Migrate & Reindex All** → confirm dialog
3. Progress panel shows `File N/M`, current `relativePath`, 5-phase ingest log
4. Each file reaches **neo4j_upsert DONE** before advancing
5. All files show **INDEXED** badge after completion



## Flow 3 — Single-file reindex (5 phases on finish)

1. Select one file → **Reindex**
2. Workflow log shows all 5 phases; final poll shows neo4j_upsert DONE (not cleared early)



## Flow 4 — Search on migrated doc

1. POST search with query matching a vault file
2. Hits include `parent_id`, `child_id`, `parent_content`



## Automated tests (CP-1.61C)

```bash
docker compose run --rm api-worker pytest \
  tests/test_neo4j_ingestion_purge.py \
  tests/test_ingest_progress_finished.py \
  tests/test_api_v16.py -q
```



## Sign-off

- [x] CLI migration + Library migrate both pass
- [x] No orphan v1.6 Neo4j nodes
- [x] 5-phase ingest visible on finished jobs