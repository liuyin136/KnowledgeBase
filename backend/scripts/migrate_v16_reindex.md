# Phase 1.6 migration — full vault reindex (hard cutover)

After deploying v1.6, **all vault files must be reindexed** before search returns results.

## Why

- Flat `:KnowledgeChunk` nodes are replaced by `:Knowledgechunk` / `:Knowledgechunk_sen` / `:Knowledgechunk_grand`.
- Vector and fulltext indexes target `:Knowledgechunk_sen` only.
- Search cache keys include `v16` suffix (old cache entries are ignored).

## Steps

1. Deploy infrastructure:
   ```bash
   docker compose build api-worker
   docker compose restart api-worker backend neo4j
   ```
2. Apply Neo4j DDL (if not auto-run):
   ```bash
   docker compose exec api-worker python scripts/init_neo4j.py
   ```
3. Reindex every file:
   - **UI:** Library → select file → Reindex (or Save & Re-ingest in editor)
   - **Bulk:** Rescan then reindex pending/error files
4. Verify search:
   ```bash
   curl -X POST http://localhost:8000/api/v1/search \
     -H "Content-Type: application/json" \
     -d '{"query":"test query","coarse_dim":256}'
   ```

## Exit checklist (CP-1.6C)

- [ ] Ingest shows 5-phase workflow progress in library UI
- [ ] Neo4j has `HAS_SECTION` / `HAS_CHILD` / `HAS_GRANDCHILD` edges for a test doc
- [ ] Search hits include `parent_id`, `child_id`, `parent_content`
- [ ] Legacy `:KnowledgeChunk` count is 0 after reindex
- [ ] `retrieval_tree` saved in Redis on rerank confirm/skip
