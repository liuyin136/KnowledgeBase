# Incident index

Short records of **closed** bugs. Grep here before re-debugging. During BUILD, grep [pitfalls](../pitfalls/) first for dead-end lessons. Promote to [ADR](../decisions/) only when API/schema policy changes.

| ID | Symptom | Status | Doc | Regression |
|----|---------|--------|-----|------------|
| INC-001 | Vault empty but Neo4j orphan nodes after delete | closed | [INC-001](INC-001-neo4j-delete-orphan.md) | `tests/test_vault_batch.py`, `tests/test_neo4j_ingestion_purge.py` |
| INC-002 | HTTP API stale after code fix; `docker exec python` sees new code | closed | [INC-002](INC-002-stale-uvicorn-backend.md) | `docker compose up -d --force-recreate backend` |
| INC-003 | Rerank `query embed position out of range`; embed returned 512 rows | closed | [INC-003](INC-003-rerank-n-batch-512.md) | `tests/test_rerank_tokens.py` |
| INC-004 | LWW re-extract stuck at version 1; Liquid YAML/JSON parse fails pre-merge | closed | [INC-004](INC-004-liquid-extract-parse-lww-blocked.md) | `tests/test_liquid_extract_parser.py`, `tests/test_memory_extract.py` |
| INC-005 | Phase 2.01 GLiNER2/Qwen3 build: snapshot_download + gliner2 --no-deps missing pydantic | closed | [INC-005](INC-005-snapshot-download-extraction-models.md) | `docker compose build api-worker`, `tests/test_gliner_loader.py`, `tests/test_qwen_loader.py` |
| INC-006 | api-worker build: sentencepiece wheel build on Python 3.14 | closed | [INC-006](INC-006-api-worker-py314-sentencepiece-build.md) | `docker compose build api-worker` |

**Drafts** from DEBUG stop hook: `INC-DRAFT-*.md` — review, rename to `INC-NNN-*`, update this table.



