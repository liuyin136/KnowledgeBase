from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_search_returns_span_id_and_job_id():
    with (
        patch("app.routers.search.search_cache.get_cached", return_value=None),
        patch("app.routers.search.enqueue_hybrid_search", return_value="job-test-1"),
    ):
        res = client.post(
            "/api/v1/search",
            json={"query": "hybrid search test", "coarse_dim": 256},
        )
    assert res.status_code == 200
    data = res.json()
    assert data["cached"] is False
    assert data["job_id"] == "job-test-1"
    assert data["span_id"]


def test_job_status_maps_awaiting_rerank():
    from unittest.mock import MagicMock

    fusion_result = {
        "status": "awaiting_rerank",
        "rerank_token_count": 42000,
        "rerank_ctx_limit": 131072,
        "rerank_doc_count": 10,
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
        "workflow_log": [],
        "span_id": "span-1",
    }
    job = MagicMock()
    job.get_status.return_value = "finished"
    job.is_finished = True
    job.is_failed = False
    job.result = fusion_result
    job.exc_info = None

    with patch("app.routers.jobs.Job.fetch", return_value=job):
        res = client.get("/api/v1/jobs/job-fusion-1")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "awaiting_rerank"
    assert data["rerank_preview"]["rerank_token_count"] == 42000


def test_job_status_returns_progress_when_started():
    from unittest.mock import MagicMock

    job = MagicMock()
    job.get_status.return_value = "started"
    job.is_finished = False
    job.is_failed = False
    job.result = None
    job.exc_info = None

    progress_payload = {
        "workflow_log": [
            {
                "phase": "query_embed",
                "status": "done",
                "latency_ms": 120,
                "model": "jina-retrieval",
            }
        ],
        "active_phase": "coarse_ann",
        "span_id": "span-live",
    }

    with (
        patch("app.routers.jobs.Job.fetch", return_value=job),
        patch("app.routers.jobs.search_progress.load_progress", return_value=progress_payload),
    ):
        res = client.get("/api/v1/jobs/job-fusion-live")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "started"
    assert data["progress"]["active_phase"] == "coarse_ann"
    assert data["progress"]["workflow_log"][0]["phase"] == "query_embed"
    assert data["progress"]["span_id"] == "span-live"


def test_rerank_confirm_skip_returns_fusion_hits():
    pending = {
        "hits_fusion": [
            {
                "chunk_id": "c1",
                "parent_path": "news/a.md",
                "chunk_index": 0,
                "content_preview": "preview",
                "final_score": 1.0,
                "display_score": 0.9,
                "rerank_score": None,
            }
        ],
        "fusion_meta": {
            "pool_size": 1,
            "w1": 0.7,
            "w2": 0.3,
            "recall_k": 50,
            "rerank_k": 10,
            "coarse_dim": 256,
            "rescore_dim": 1024,
            "latency_ms": 50,
        },
        "workflow_log": [
            {"phase": "hybrid_fusion", "status": "done", "latency_ms": 10}
        ],
        "span_id": "span-skip",
    }
    fusion_result = {
        "status": "awaiting_rerank",
        "rerank_token_count": 1000,
        "rerank_ctx_limit": 131072,
        "rerank_doc_count": 1,
        "hits": pending["hits_fusion"],
        "fusion_meta": pending["fusion_meta"],
        "workflow_log": pending["workflow_log"],
        "span_id": "span-skip",
    }
    from unittest.mock import MagicMock

    job = MagicMock()
    job.is_finished = True
    job.result = fusion_result

    with (
        patch("app.routers.jobs.Job.fetch", return_value=job),
        patch("app.routers.jobs.pending_rerank.load_pending", return_value=pending),
        patch("app.routers.jobs.pending_rerank.delete_pending") as mock_delete,
    ):
        res = client.post("/api/v1/jobs/job-fusion-2/rerank", json={"confirm": False})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "skipped_rerank"
    assert data["hits"][0]["rerank_score"] is None
    mock_delete.assert_called_once_with("job-fusion-2")


def test_rerank_confirm_true_enqueues_rerank_job():
    pending = {"span_id": "span-go", "query": "q", "rerank_inputs": ["a"], "rerank_k": 10}
    fusion_result = {
        "status": "awaiting_rerank",
        "rerank_token_count": 500,
        "rerank_ctx_limit": 131072,
        "rerank_doc_count": 1,
        "fusion_meta": {"rerank_k": 10},
        "hits": [],
        "workflow_log": [],
        "span_id": "span-go",
    }
    from unittest.mock import MagicMock

    job = MagicMock()
    job.is_finished = True
    job.result = fusion_result

    with (
        patch("app.routers.jobs.Job.fetch", return_value=job),
        patch("app.routers.jobs.pending_rerank.load_pending", return_value=pending),
        patch("app.routers.jobs.enqueue_hybrid_rerank", return_value="rerank-job-9") as mock_enqueue,
    ):
        res = client.post("/api/v1/jobs/job-fusion-3/rerank", json={"confirm": True})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "rerank_started"
    assert data["rerank_job_id"] == "rerank-job-9"
    mock_enqueue.assert_called_once_with("job-fusion-3")


def test_search_rejects_invalid_weight_sum():
    res = client.post(
        "/api/v1/search",
        json={"query": "test", "w1": 0.8, "w2": 0.3, "coarse_dim": 256},
    )
    assert res.status_code == 422


def test_search_cache_hit():
    cached_payload = {
        "hits": [],
        "fusion_meta": {
            "pool_size": 0,
            "w1": 0.7,
            "w2": 0.3,
            "recall_k": 50,
            "rerank_k": 10,
            "coarse_dim": 256,
            "rescore_dim": 1024,
            "latency_ms": 10,
            "vram_peak_mb": 0,
        },
        "workflow_log": [
            {
                "phase": "query_embed",
                "status": "done",
                "latency_ms": 5,
                "model": "jina-retrieval",
            }
        ],
        "span_id": "cached-span",
    }
    with patch("app.routers.search.search_cache.get_cached", return_value=cached_payload):
        res = client.post(
            "/api/v1/search",
            json={"query": "cached query", "coarse_dim": 256},
        )
    assert res.status_code == 200
    data = res.json()
    assert data["cached"] is True
    assert data["span_id"] == "cached-span"
    assert data["workflow_log"][0]["phase"] == "query_embed"


def test_search_empty_allowlist_fast_path():
    with patch(
        "app.routers.search.resolve_search_allowlist",
        return_value=[],
    ):
        res = client.post(
            "/api/v1/search",
            json={
                "query": "scoped empty",
                "coarse_dim": 256,
                "folder_ids": ["f-empty"],
            },
        )
    assert res.status_code == 200
    data = res.json()
    assert data["hits"] == []
    assert data["job_id"] is None
    assert data["workflow_log"][0]["phase"] == "vault_scope"


def test_search_allowlist_too_large_returns_422():
    from app.services.vault_scope import AllowlistTooLargeError

    with patch(
        "app.routers.search.resolve_search_allowlist",
        side_effect=AllowlistTooLargeError("narrow filters"),
    ):
        res = client.post(
            "/api/v1/search",
            json={"query": "too many", "coarse_dim": 256, "folder_ids": ["f1"]},
        )
    assert res.status_code == 422


def test_search_scoped_cache_key_differs():
    cached_payload = {
        "hits": [],
        "fusion_meta": {
            "pool_size": 0,
            "w1": 0.7,
            "w2": 0.3,
            "recall_k": 50,
            "rerank_k": 10,
            "coarse_dim": 256,
            "rescore_dim": 1024,
            "latency_ms": 10,
            "allowlist_size": 1,
        },
        "workflow_log": [
            {
                "phase": "vault_scope",
                "status": "done",
                "latency_ms": 0,
                "hit_count": 1,
            }
        ],
        "span_id": "scoped-span",
    }
    with (
        patch("app.routers.search.resolve_search_allowlist", return_value=["news/a.md"]),
        patch("app.routers.search.search_cache.get_cached", return_value=cached_payload),
    ):
        res = client.post(
            "/api/v1/search",
            json={
                "query": "scoped cached",
                "coarse_dim": 256,
                "folder_ids": ["f-news"],
            },
        )
    assert res.status_code == 200
    data = res.json()
    assert data["cached"] is True
    assert data["workflow_log"][0]["phase"] == "vault_scope"
