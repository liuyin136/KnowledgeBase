# CP-C E2E Verification — Phase 1 RAG Console

Manual browser checklist for Phase 1 exit gate. Run with stack up:

```bash
docker compose up -d
docker compose --profile otel up -d jaeger   # optional, for span_id in Jaeger UI
```

## Prerequisites

- [ ] `http://localhost:8000/health` returns OK
- [ ] `http://localhost:3000` home shows links to `/rag` and `/experiment`

## Flow 1 — Search + cache

1. Open `http://localhost:3000/rag/search`
2. Enter query (min 2 chars), e.g. `redis connection pool`
3. Submit → loading skeletons → ranked results with scores
4. Footer shows `span_id`
5. Repeat **identical** query + fusion settings → **CACHED** label appears

## Flow 2 — Library create → ingest → search

1. Open `http://localhost:3000/rag/library/create`
2. Create RND document with distinctive content (e.g. title `cpc-e2e`, results field with unique phrase `cpc-e2e-marker-2026`)
3. Wait for ingest poll → redirect to library with success toast
4. Library list shows **INDEXED** badge for new file
5. Search `cpc-e2e-marker-2026` on `/rag/search` → new doc appears in top results

## Flow 3 — Edit + re-ingest

1. Edit the document from library; change results field
2. Save & Re-ingest → toast confirms completion
3. Search updated phrase → results reflect change

## Flow 4 — Observability (optional)

1. With Jaeger profile: open `http://localhost:16686`
2. Run search from `/rag/search`
3. Trace visible; `span_id` in footer matches span in Jaeger

## API smoke (curl)

```bash
curl -s -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query":"redis pool","coarse_dim":256}'

# Repeat identical POST → "cached": true
```

## Automated tests

```bash
docker compose run --rm \
  -v "${PWD}/tests:/app/tests" \
  -v "${PWD}/backend/app:/app/app" \
  api-worker python -m pytest \
  tests/test_chunking.py tests/test_fusion.py tests/test_hybrid_benchmark.py \
  tests/test_hybrid_integration.py -q
```

## Sign-off

- [ ] All flows pass
- [ ] `hybrid_ndcg@10 > vector_ndcg@10` (unit benchmark + GPU integration when VRAM allows)
- [ ] Human review before Phase 2

## User Confirmation in Phase1 at 2026/07/11 14:00

All workflow pass
