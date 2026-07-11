from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services import search_progress


def test_search_progress_roundtrip():
    with patch("app.services.search_progress.get_redis_connection") as mock_conn:
        store: dict[str, str] = {}

        def setex(key, ttl, value):
            store[key] = value

        def get(key):
            return store.get(key)

        def delete(key):
            store.pop(key, None)

        redis_mock = MagicMock()
        redis_mock.setex.side_effect = setex
        redis_mock.get.side_effect = get
        redis_mock.delete.side_effect = delete
        mock_conn.return_value = redis_mock

        search_progress.init_progress("job-1", active_phase="query_embed", span_id="span-abc")
        loaded = search_progress.load_progress("job-1")
        assert loaded == {
            "workflow_log": [],
            "active_phase": "query_embed",
            "span_id": "span-abc",
        }

        workflow_log = [
            {"phase": "query_embed", "status": "done", "latency_ms": 42, "model": "jina-retrieval"}
        ]
        search_progress.update_progress("job-1", workflow_log, "coarse_ann", span_id="span-abc")
        loaded = search_progress.load_progress("job-1")
        assert loaded["workflow_log"] == workflow_log
        assert loaded["active_phase"] == "coarse_ann"

        search_progress.clear_progress("job-1")
        assert search_progress.load_progress("job-1") is None


def test_enqueue_fusion_inits_progress():
    from unittest.mock import MagicMock as MM

    with (
        patch("app.services.job_queue.get_queue") as mock_queue,
        patch("app.services.search_progress.init_progress") as mock_init,
    ):
        job = MM()
        job.id = "fusion-job-99"
        mock_queue.return_value.enqueue.return_value = job

        from app.services.job_queue import enqueue_hybrid_search_fusion

        job_id = enqueue_hybrid_search_fusion(
            query="test query",
            w1=0.7,
            w2=0.3,
            recall_k=50,
            rerank_k=10,
            coarse_dim=256,
            use_minmax_fallback=False,
            traceparent="",
            cache_key="cache-1",
            span_id="span-init",
            allowed_paths=["news/a.md"],
            scope_meta={"folder_ids": ["f1"]},
        )
        assert job_id == "fusion-job-99"
        mock_init.assert_called_once_with(
            "fusion-job-99",
            active_phase="vault_scope",
            span_id="span-init",
        )
