# CP-1.62 E2E Verification — Hierarchical Chunk v2

Manual checklist for Phase 1.62 exit gate. Stack must be up:

```bash
docker compose up -d
docker compose exec api-worker python scripts/init_neo4j.py
```

## Prerequisites

- [x] Phase 1.61 code present
- [x] `http://localhost:8000/health` OK
- [x] User understands **default reconstruct deletes vault disk files**

## Flow 1 — Destructive reconstruct (dry-run then live)

```bash
docker compose run --rm api-worker python scripts/vault_reset_and_reindex.py --dry-run
docker compose run --rm api-worker python scripts/vault_reset_and_reindex.py
```

- [x] Dry-run reports disk file count to delete
- [x] Live run leaves empty vault + clean Neo4j
- [x] Re-upload library files via `/rag/library`



## Flow 2 — 10-phase ingest UI

1. Upload or Save & Re-ingest a file
2. Confirm workflow shows: front_matter → family → parent → child → grandchild → embed×4 → neo4j_upsert
3. All phases reach DONE



## Flow 3 — Search cascade workflow

1. Open `/rag/search`
2. Submit query
3. Workflow shows: query_embed → family_recall → parent_recall → child_recall → grandchild_recall → hierarchical_fusion → rerank (awaiting)
4. Result cards show **vector** score (not rerank)



## Flow 4 — Rerank soft gate

1. If prompt tokens > 8192, dialog warns about soft gate
2. Skip → hits ordered by hierarchical fusion final score



## Flow 5 — Doc meta

```sql
SELECT * FROM vault_doc_meta LIMIT 5;
```

- [x] Rows exist for files that had YAML / preamble metadata



## Automated tests

```bash
docker compose run --rm api-worker pytest \
  tests/test_front_matter.py \
  tests/test_hierarchical_chunking_v162.py \
  tests/test_neo4j_v162_schema.py \
  tests/test_hierarchical_fusion.py -q
```



## Sign-off

- [x] Reconstruct + re-upload + search pass
- [x] 4 Neo4j tiers embedded
- [x] SQLite `vault_doc_meta` populated