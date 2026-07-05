# v1.3 API Worker Fix — Missing RQ Entry Point

**Version**: 1.3  
**Date**: 2026-07-05  
**Status**: Fixed  
**Related issues**: Repeated container restarts and log spam from `api-worker` service  
**Companion docs**: `docker/docker-compose.yml`, `backend/app/workers/`, `upload/v1.3-docker-design-decision.md`

---

## 1. Problem

Running `docker compose logs api-worker` produced repeated failures:

```
/usr/bin/python: No module named app.workers.worker
```

The container entered a restart loop because of `restart: unless-stopped` in the service definition. This made the service unusable and polluted logs.

---

## 2. Root Cause Analysis

### Compose Configuration
In `docker/docker-compose.yml`, the `api-worker` service was defined with:

```yaml
api-worker:
  build: ...
  container_name: raglab-api-worker
  command: ["python", "-m", "app.workers.worker"]
  environment:
    ...
    RQ_QUEUE_NAME: default
    WORKER_CONCURRENCY: "1"
  ...
  restart: unless-stopped
```

The command instructed Python to execute the module `app.workers.worker`.

### Missing Implementation
The directory `backend/app/workers/` only contained:

- `__init__.py`
- `progress.py`
- `tasks.py`

There was **no** `worker.py` file.

### Design vs. Reality
Comments in the existing worker modules indicated the original intent:

- `backend/app/workers/tasks.py` (docstring):
  > "In production, the same task functions can be invoked by the `api-worker` service (an RQ worker reading from the same Redis queue) with no code changes."

- `backend/app/workers/progress.py`:
  > "...the docker-compose `api-worker` service can run the same code via `python -m app.workers.worker` reading jobs from an RQ queue"

The architecture planned for:
- Job enqueueing via RQ (Redis Queue)
- A dedicated long-running worker process in a separate container

However, the actual implementation used **FastAPI `BackgroundTasks`** inside the main `backend` service (`api/v1/ingest.py` and `api/v1/search.py` call `background_tasks.add_task(run_ingest_task, ...)`).

The RQ worker entrypoint was never implemented, even though:
- `rq` is listed in `backend/requirements.txt`
- Environment variables (`RQ_QUEUE_NAME`, `WORKER_CONCURRENCY`) were wired in compose
- The `agent-ctx/3-full-stack-developer-docker.md` even noted: *"If you implement RQ, that module should..."*

Because of the missing module + restart policy, the error kept repeating on every container start attempt.

---

## 3. Solution

Implemented the missing RQ worker entrypoint at `backend/app/workers/worker.py`.

The new module:
- Follows the project's structured JSON logging (`configure_logging`)
- Connects to Redis using the existing `REDIS_URL`
- Listens on the configured `RQ_QUEUE_NAME`
- Imports `app.workers.tasks` (side-effect import to register the task functions for RQ)
- Starts a standard `rq.Worker` and blocks on `worker.work()`
- Includes basic startup logging and error handling

---

## 4. Changes Made

| File                              | Change                  | Description |
|-----------------------------------|-------------------------|-----------|
| `backend/app/workers/worker.py`   | **New file**            | Full RQ worker implementation as the entrypoint for `python -m app.workers.worker` |

No changes were required to `docker-compose.yml` (the command was already correct).

---

## 5. Implementation Highlights (`worker.py`)

- Uses the same `app.core.logging.configure_logging()` for consistency with the main backend.
- Performs a fast `redis_conn.ping()` on startup.
- Creates a single `Queue` based on `RQ_QUEUE_NAME`.
- Names the worker with PID for easier identification in logs (`rag-api-worker-{pid}`).
- The side-effect import `from app.workers import tasks` ensures `run_ingest_task` and `run_search_task` are discoverable by RQ when jobs are eventually enqueued with dotted paths.
- Graceful handling for `KeyboardInterrupt` and unexpected fatal errors.

The implementation keeps heavy initialization (embedding models, orchestrator) lazy — they are loaded inside the task functions on first execution (via the singleton pattern already present in `tasks.py`).

---

## 6. Verification

After the fix:

```bash
# Rebuild the image (required because worker.py was added after build)
docker compose build api-worker

# Recreate the service
docker compose up -d --force-recreate api-worker

# Check logs
docker compose logs -f api-worker
```

Expected successful output (instead of module-not-found errors):

- `worker.starting`
- `worker.ready`
- The worker should stay running (no restarts)

Also verify:

```bash
docker compose ps
# api-worker should show as "Up" (not "Restarting")
```

The main `backend` service continues to function normally using its in-process `BackgroundTasks`.

---

## 7. Notes and Future Considerations

- **Current dispatch path unchanged**: Jobs are still started via FastAPI `BackgroundTasks` inside the `backend` container. The new `api-worker` is now capable of consuming RQ jobs, but nothing is enqueuing to RQ yet.

- **To fully activate the RQ path** (for scaling / isolation):
  - Modify `api/v1/ingest.py` and `api/v1/search.py` to use `queue.enqueue(...)` (or `rq.job.Job`) instead of (or in addition to) `BackgroundTasks`.
  - The task functions in `tasks.py` are already designed to be callable by both mechanisms.

- This fix resolves the immediate crash/restart problem and completes the originally planned service definition.

- The worker respects the same environment variables and model configuration as the main backend.

---

## 8. Related Files

- `docker/docker-compose.yml` — api-worker service definition
- `backend/app/workers/tasks.py` — the actual task implementations (`run_ingest_task`, `run_search_task`)
- `backend/app/workers/progress.py` — shared Redis-backed job state
- `backend/app/api/v1/ingest.py` & `search.py` — current job dispatch points
- `agent-ctx/3-full-stack-developer-docker.md` — historical note about the intended worker entrypoint

---

**Status**: Problem resolved. The `api-worker` service can now start successfully.