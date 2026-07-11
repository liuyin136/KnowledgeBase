# Phase 1 — Hybrid Search MVP (Checkpoint-Driven)

Implementation completed per checkpoint plan. See `tasks/todo.md` for checklist.

## Key changes

- **Chunking:** Fixed tail-discard to use global token overlap (plan Task 1.2)
- **Fusion:** Added `compute_recall_at_k`; benchmark reports recall@5
- **API:** `w1 + w2` validation; `ingest_job_id` on save response
- **Tests:** GPU integration via RQ (skips if CUDA OOM); synthetic benchmark gate
- **Frontend:** RagShell sidebar, skeletons, date filter, ingest job polling
- **Docker:** Mount `backend/app`, `tests` on api-worker for dev verification

## Verification

```bash
docker compose exec -e IN_WORKER_EXEC=1 api-worker python -m pytest \
  tests/test_chunking.py tests/test_fusion.py tests/test_hybrid_benchmark.py \
  tests/test_search_schemas.py tests/test_hybrid_integration.py -q
```

Manual E2E: `tasks/CP-C-E2E.md`

Benchmark ingest (optional, run when GPU idle):

```bash
docker compose exec -e ALLOW_BENCHMARK_INGEST=1 api-worker python scripts/ingest_benchmark_fixture.py
```
