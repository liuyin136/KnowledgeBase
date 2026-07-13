# Phase 1.61 migration — full vault reindex (hard cutover patch)

After deploying Phase 1.61, use **one-shot full migration** to purge incomplete v1.6
Neo4j nodes, clear Redis caches, reset vault metadata, and reindex all library files.

## Why

- `delete_all_knowledge()` only removed `:Knowledge` + `:KnowledgeChunk`, leaving orphan
  `:Knowledgechunk*` and `:LogFile` nodes.
- Ingest progress cleared Redis before the UI could see the 5th phase (`neo4j_upsert`).
- Library had single-file Reindex only; bulk migration is required for v1.6 cutover.

## Steps

1. Deploy app changes (no new Docker deps):
   ```bash
   docker compose restart api-worker backend
   ```
2. Apply Neo4j DDL (if not auto-run):
   ```bash
   docker compose exec api-worker python scripts/read-only/init_neo4j.py
   ```
   Or use the convenience wrapper:
   ```bash
   docker compose exec api-worker python scripts/init_neo4j.py
   ```
3. **Full migration (recommended):**
   ```bash
   docker compose run --rm api-worker python scripts/vault_reset_and_reindex.py --dry-run
   docker compose run --rm api-worker python scripts/vault_reset_and_reindex.py
   ```
   Or in Library UI: **Migrate & Reindex All**
4. Verify search:
   ```bash
   curl -X POST http://localhost:8000/api/v1/search \
     -H "Content-Type: application/json" \
     -d '{"query":"test query","coarse_dim":256}'
   ```

## Exit checklist (CP-1.61C)

- [ ] Ingest shows 5-phase workflow progress in library UI (including neo4j_upsert DONE)
- [ ] Full migration CLI completes without orphan v1.6 nodes
- [ ] Neo4j has `HAS_SECTION` / `HAS_CHILD` / `HAS_GRANDCHILD` edges for vault docs
- [ ] Search hits include `parent_id`, `child_id`, `parent_content`
- [ ] Legacy `:KnowledgeChunk` count is 0 after migration
- [ ] `MATCH (p:Knowledgechunk) WHERE NOT (()-[:HAS_SECTION]->(p)) RETURN count(p)` = 0

## Verification Cypher

```cypher
MATCH (c:KnowledgeChunk) RETURN count(c) AS legacy_chunks;
MATCH (p:Knowledgechunk) WHERE NOT (()-[:HAS_SECTION]->(p)) RETURN count(p) AS orphan_parents;
```
