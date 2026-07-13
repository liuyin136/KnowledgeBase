# INC-002 — Stale uvicorn after mounted code change

## Status

closed

## Date

2026-07-12

## Symptom

`docker exec raglab-backend python` imports show fixed code; HTTP API via port 8000 still runs old behavior after `docker compose restart backend`.

## Root cause

Uvicorn worker process did not reload Python modules from volume mount; restart alone insufficient.

## Fix

`docker compose up -d --force-recreate backend` to pick up mounted `backend/app` changes.

## Files touched

- (ops only — no app code)

## Regression

After backend code change:

```bash
docker compose restart backend
curl http://localhost:8000/health
# If behavior wrong:
docker compose up -d --force-recreate backend
```

## ADR

None. Documented in [AGENTS.md](../../AGENTS.md) and [docker-build.mdc](../../.cursor/rules/docker-build.mdc).
