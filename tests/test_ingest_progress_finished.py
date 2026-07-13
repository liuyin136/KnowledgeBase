from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_job_status_returns_ingest_progress_when_finished():
    workflow_log = [
        {"phase": "ast_split", "status": "done", "latency_ms": 10, "parent_count": 2},
        {"phase": "child_split", "status": "done", "latency_ms": 20, "child_count": 5},
        {"phase": "grandchild_split", "status": "done", "latency_ms": 15, "grandchild_count": 12},
        {"phase": "embed_children", "status": "done", "latency_ms": 500, "embedded_count": 5},
        {"phase": "neo4j_upsert", "status": "done", "latency_ms": 30},
    ]
    job = MagicMock()
    job.get_status.return_value = "finished"
    job.is_finished = True
    job.is_failed = False
    job.result = {
        "children_written": 5,
        "workflow_log": workflow_log,
        "relative_path": "news/a.md",
    }
    job.exc_info = None

    with (
        patch("app.routers.jobs.Job.fetch", return_value=job),
        patch("app.routers.jobs.search_progress.load_progress", return_value=None),
        patch("app.routers.jobs.ingest_progress.load_progress", return_value=None),
    ):
        res = client.get("/api/v1/jobs/job-ingest-done")
    assert res.status_code == 200
    data = res.json()
    assert data["ingest_progress"]["active_phase"] is None
    assert len(data["ingest_progress"]["workflow_log"]) == 5
    assert data["ingest_progress"]["relative_path"] == "news/a.md"
    assert data["ingest_progress"]["workflow_log"][-1]["phase"] == "neo4j_upsert"
