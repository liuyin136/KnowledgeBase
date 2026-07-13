"""Regression tests for search job status after fusion (Phase 1.63)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_finished_search_job_with_v162_workflow_log_does_not_attach_ingest_progress():
    """Search fusion jobs must not parse workflow_log as IngestPhase."""
    fusion_result = {
        "status": "awaiting_rerank",
        "rerank_token_count": 1200,
        "rerank_ctx_limit": 131072,
        "rerank_doc_count": 5,
        "hits": [],
        "fusion_meta": {
            "pool_size": 5,
            "w1": 0.7,
            "w2": 0.3,
            "recall_k": 50,
            "rerank_k": 10,
            "coarse_dim": 256,
            "rescore_dim": 1024,
            "latency_ms": 100,
        },
        "workflow_log": [
            {"phase": "vault_scope", "status": "done", "latency_ms": 1, "hit_count": 3},
            {"phase": "query_embed", "status": "done", "latency_ms": 120, "model": "jina-retrieval"},
            {"phase": "family_recall", "status": "done", "latency_ms": 40, "hit_count": 10},
            {"phase": "parent_recall", "status": "done", "latency_ms": 35, "hit_count": 8},
            {"phase": "child_recall", "status": "done", "latency_ms": 30, "hit_count": 6},
            {"phase": "grandchild_recall", "status": "done", "latency_ms": 25, "hit_count": 5},
            {
                "phase": "hierarchical_fusion",
                "status": "done",
                "latency_ms": 2,
                "pool_size": 5,
                "w1": 0.7,
                "w2": 0.3,
                "rerank_k": 10,
            },
        ],
        "span_id": "span-v162",
    }
    job = MagicMock()
    job.get_status.return_value = "finished"
    job.is_finished = True
    job.is_failed = False
    job.result = fusion_result
    job.exc_info = None

    with (
        patch("app.routers.jobs.Job.fetch", return_value=job),
        patch("app.routers.jobs.search_progress.load_progress", return_value=None),
        patch("app.routers.jobs.ingest_progress.load_progress", return_value=None),
    ):
        res = client.get("/api/v1/jobs/job-fusion-v162")

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "awaiting_rerank"
    assert "ingest_progress" not in data
    assert data["rerank_preview"]["rerank_token_count"] == 1200
    assert data["result"]["workflow_log"][0]["phase"] == "vault_scope"
