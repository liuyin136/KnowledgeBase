"""
workers/progress.py — Redis-backed job progress tracking + status polling.

Per the v1.2 directive, the FastAPI backend uses Redis for the job queue + job
state. We persist job state to Redis so polling works across requests AND
across worker processes (BackgroundTasks run in-process by default; in
production the docker-compose `api-worker` service can run the same code via
`python -m app.workers.worker` reading jobs from an RQ queue — same Redis
schema, different consumer).

Redis key layout:
  • rag:job:{jobId}               — hash with: type, status, progress, current,
                                    total, experiment_id, error_code,
                                    error_message, search_id, created_at,
                                    updated_at, result_json
  • rag:job:{jobId}:events        — list of JSON-encoded IngestProgressEvents
                                    (newest first via LPUSH; capped at 200)
  • rag:jobs:index                — sorted set (score=created_at) of all job ids

All keys TTL at settings.job_ttl_seconds (default 24h) so completed jobs
eventually expire. The frontend polls `GET /api/v1/ingest/{jobId}/status`
or `GET /api/v1/jobs/{jobId}` — both read from the same Redis-backed state.

If Redis is unreachable, we fall back to an in-memory dict so the backend
still functions (degraded — progress won't survive a worker restart). This
makes local dev without Redis possible.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import redis

from app.core.config import settings
from app.core.constants import JobStatus, JobType
from app.core.exceptions import JobNotFoundError
from app.core.logging import get_logger
from app.schemas.ingest import IngestProgressEvent, JobStatusResponse
from app.schemas.search import SearchResponse

logger = get_logger("rag.workers.progress")

_EVENTS_MAX_LEN = 200


# ─── In-memory fallback (used when Redis is unavailable) ──────────────────────

class _InMemoryJobStore:
    """Thread-safe in-memory job store — used as a Redis fallback."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._events: Dict[str, List[Dict[str, Any]]] = {}

    def hset(self, key: str, mapping: Dict[str, Any]) -> None:
        job_id = key.split(":")[-1]
        with self._lock:
            self._jobs.setdefault(job_id, {}).update(mapping)

    def hgetall(self, key: str) -> Dict[str, Any]:
        job_id = key.split(":")[-1]
        with self._lock:
            return dict(self._jobs.get(job_id, {}))

    def lpush(self, key: str, *values: str) -> None:
        job_id = key.split(":")[-1]
        with self._lock:
            self._events.setdefault(job_id, [])
            for v in values:
                self._events[job_id].insert(0, json.loads(v))
            # Cap
            if len(self._events[job_id]) > _EVENTS_MAX_LEN:
                self._events[job_id] = self._events[job_id][:_EVENTS_MAX_LEN]

    def lrange(self, key: str, start: int, end: int) -> List[str]:
        job_id = key.split(":")[-1]
        with self._lock:
            evts = self._events.get(job_id, [])
            if end == -1:
                slc = evts[start:]
            else:
                slc = evts[start : end + 1]
            return [json.dumps(e) for e in slc]

    def expire(self, key: str, ttl: int) -> None:
        # No-op — in-memory store doesn't TTL.
        pass

    def zadd(self, key: str, mapping: Dict[str, float]) -> None:
        # Not strictly needed for the in-memory fallback.
        pass


# ─── Progress tracker (Redis primary, in-memory fallback) ────────────────────


class ProgressTracker:
    """Job state + progress events. Redis-backed with in-memory fallback."""

    def __init__(self, redis_url: Optional[str] = None) -> None:
        self._redis_url = redis_url or settings.redis_url
        self._redis: Optional[redis.Redis] = None
        self._fallback = _InMemoryJobStore()
        self._use_fallback = False
        self._connect()

    def _connect(self) -> None:
        try:
            self._redis = redis.from_url(self._redis_url, decode_responses=True)
            self._redis.ping()
            self._use_fallback = False
            logger.info("progress.redis.ok", extra={"event": "progress.redis.ok", "url": self._redis_url})
        except Exception as exc:
            self._use_fallback = True
            logger.warning(
                "progress.redis.fallback",
                extra={
                    "event": "progress.redis.fallback",
                    "url": self._redis_url,
                    "error": str(exc),
                },
            )

    # ─── job lifecycle ─────────────────────────────────────────────────────

    def create_job(
        self,
        *,
        job_id: Optional[str] = None,
        job_type: JobType,
        experiment_id: Optional[str] = None,
        search_id: Optional[str] = None,
    ) -> str:
        """Create a new job record. Returns the job id."""
        jid = job_id or str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        mapping = {
            "job_id": jid,
            "type": job_type.value,
            "status": JobStatus.QUEUED.value,
            "progress": "0.0",
            "current": "0",
            "total": "0",
            "experiment_id": experiment_id or "",
            "search_id": search_id or "",
            "error_code": "",
            "error_message": "",
            "result_json": "",
            "created_at": now,
            "updated_at": now,
        }
        self._hset(f"rag:job:{jid}", mapping)
        self._zadd("rag:jobs:index", {jid: time.time()})
        self._expire(f"rag:job:{jid}", settings.job_ttl_seconds)
        self._expire(f"rag:job:{jid}:events", settings.job_ttl_seconds)
        return jid

    def mark_running(self, job_id: str, total: int = 0) -> None:
        self._hset(
            f"rag:job:{job_id}",
            {
                "status": JobStatus.RUNNING.value,
                "total": str(total),
                "updated_at": datetime.utcnow().isoformat(),
            },
        )

    def mark_completed(self, job_id: str, result: Optional[Any] = None) -> None:
        mapping: Dict[str, Any] = {
            "status": JobStatus.COMPLETED.value,
            "progress": "100.0",
            "updated_at": datetime.utcnow().isoformat(),
        }
        if result is not None:
            # result must be a SearchResponse (for search jobs) — serialize to JSON.
            if hasattr(result, "model_dump_json"):
                mapping["result_json"] = result.model_dump_json()
            elif isinstance(result, dict):
                mapping["result_json"] = json.dumps(result)
            else:
                mapping["result_json"] = json.dumps(result, default=str)
        self._hset(f"rag:job:{job_id}", mapping)

    def mark_failed(self, job_id: str, *, error_code: str, error_message: str) -> None:
        self._hset(
            f"rag:job:{job_id}",
            {
                "status": JobStatus.FAILED.value,
                "error_code": error_code,
                "error_message": error_message[:2000],
                "updated_at": datetime.utcnow().isoformat(),
            },
        )

    # ─── progress events ───────────────────────────────────────────────────

    def append_event(self, job_id: str, event: IngestProgressEvent) -> None:
        """Append a progress event to the job's event list + update progress/current."""
        # Update aggregate progress fields
        mapping = {
            "progress": str(round(event.progress, 2)),
            "current": str(event.index),
            "total": str(event.total),
            "updated_at": datetime.utcnow().isoformat(),
        }
        # If the event is the "done" or "error" stage, also reflect that.
        if event.stage == "done":
            mapping["status"] = JobStatus.COMPLETED.value
        elif event.stage == "error":
            mapping["status"] = JobStatus.FAILED.value
            mapping["error_message"] = (event.message or "")[:2000]
            mapping["error_code"] = "INGEST_FAILED"
        self._hset(f"rag:job:{job_id}", mapping)
        # Push event JSON
        self._lpush(f"rag:job:{job_id}:events", event.model_dump_json())

    # ─── read status ───────────────────────────────────────────────────────

    def get_status(self, job_id: str) -> JobStatusResponse:
        """Return the JobStatusResponse for a job. Raises JobNotFoundError if missing."""
        raw = self._hgetall(f"rag:job:{job_id}")
        if not raw:
            raise JobNotFoundError(
                f"Job {job_id} not found",
                details={"job_id": job_id},
            )
        # Events
        evt_jsons = self._lrange(f"rag:job:{job_id}:events", 0, _EVENTS_MAX_LEN - 1)
        events: List[IngestProgressEvent] = []
        for j in evt_jsons:
            try:
                events.append(IngestProgressEvent.model_validate_json(j))
            except Exception:
                continue
        # Result (search jobs)
        result: Optional[SearchResponse] = None
        rj = raw.get("result_json") or ""
        if rj:
            try:
                result = SearchResponse.model_validate_json(rj)
            except Exception:
                result = None

        return JobStatusResponse(
            jobId=raw.get("job_id", job_id),
            type=raw.get("type", "ingest"),
            experimentId=raw.get("experiment_id") or None,
            status=raw.get("status", "queued"),
            progress=float(raw.get("progress", 0.0)),
            current=int(raw.get("current", 0) or 0),
            total=int(raw.get("total", 0) or 0),
            events=events,
            errorCode=raw.get("error_code") or None,
            errorMessage=raw.get("error_message") or None,
            result=result,
        )

    # ─── internal dispatch (redis or fallback) ──────────────────────────────

    def _hset(self, key: str, mapping: Dict[str, Any]) -> None:
        if self._use_fallback or self._redis is None:
            self._fallback.hset(key, mapping)
        else:
            try:
                # redis-py hset requires str values
                self._redis.hset(key, mapping={k: str(v) for k, v in mapping.items()})
            except Exception as exc:
                logger.warning("progress.redis.hset_failed", extra={"error": str(exc)})
                self._fallback.hset(key, mapping)

    def _hgetall(self, key: str) -> Dict[str, Any]:
        if self._use_fallback or self._redis is None:
            return self._fallback.hgetall(key)
        try:
            return self._redis.hgetall(key) or {}
        except Exception as exc:
            logger.warning("progress.redis.hgetall_failed", extra={"error": str(exc)})
            return self._fallback.hgetall(key)

    def _lpush(self, key: str, value: str) -> None:
        if self._use_fallback or self._redis is None:
            self._fallback.lpush(key, value)
        else:
            try:
                self._redis.lpush(key, value)
                self._redis.ltrim(key, 0, _EVENTS_MAX_LEN - 1)
            except Exception as exc:
                logger.warning("progress.redis.lpush_failed", extra={"error": str(exc)})
                self._fallback.lpush(key, value)

    def _lrange(self, key: str, start: int, end: int) -> List[str]:
        if self._use_fallback or self._redis is None:
            return self._fallback.lrange(key, start, end)
        try:
            return self._redis.lrange(key, start, end)
        except Exception as exc:
            logger.warning("progress.redis.lrange_failed", extra={"error": str(exc)})
            return self._fallback.lrange(key, start, end)

    def _expire(self, key: str, ttl: int) -> None:
        if self._use_fallback or self._redis is None:
            self._fallback.expire(key, ttl)
        else:
            try:
                self._redis.expire(key, ttl)
            except Exception:
                pass

    def _zadd(self, key: str, mapping: Dict[str, float]) -> None:
        if self._use_fallback or self._redis is None:
            self._fallback.zadd(key, mapping)
        else:
            try:
                self._redis.zadd(key, mapping)
            except Exception:
                pass


# ─── Module-level singleton ───────────────────────────────────────────────────

_tracker: Optional[ProgressTracker] = None
_tracker_lock = threading.Lock()


def get_progress_tracker() -> ProgressTracker:
    global _tracker
    if _tracker is None:
        with _tracker_lock:
            if _tracker is None:
                _tracker = ProgressTracker()
    return _tracker
