from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_job_status_returns_ingest_progress_when_started():
    job = MagicMock()
    job.get_status.return_value = "started"
    job.is_finished = False
    job.is_failed = False
    job.result = None
    job.exc_info = None

    ingest_payload = {
        "workflow_log": [
            {
                "phase": "ast_split",
                "status": "done",
                "latency_ms": 12,
                "parent_count": 3,
            }
        ],
        "active_phase": "child_split",
        "relative_path": "news/a.md",
    }

    with (
        patch("app.routers.jobs.Job.fetch", return_value=job),
        patch("app.routers.jobs.search_progress.load_progress", return_value=None),
        patch("app.routers.jobs.ingest_progress.load_progress", return_value=ingest_payload),
    ):
        res = client.get("/api/v1/jobs/job-ingest-live")
    assert res.status_code == 200
    data = res.json()
    assert data["ingest_progress"]["active_phase"] == "child_split"
    assert data["ingest_progress"]["workflow_log"][0]["phase"] == "ast_split"


def test_knowledge_context_stub():
    res = client.post(
        "/api/v1/knowledge/context",
        json={
            "query": "What is RAG?",
            "parent_ids": ["p1"],
            "parent_contents": ["# Section\n\nContent here."],
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "stub"
    assert "Content here" in data["assembled_markdown"]
