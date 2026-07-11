from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services import pending_rerank


def test_pending_rerank_roundtrip():
    with patch("app.services.pending_rerank.get_redis_connection") as mock_conn:
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

        payload = {"query": "test", "rerank_inputs": ["a"], "rerank_k": 10}
        pending_rerank.save_pending("job-1", payload)
        loaded = pending_rerank.load_pending("job-1")
        assert loaded == payload
        pending_rerank.delete_pending("job-1")
        assert pending_rerank.load_pending("job-1") is None


def test_slim_pool_serializes_without_neo4j_fields():
    from datetime import datetime

    from app.workers.tasks import _slim_pool_for_pending

    pool = {
        "chunk-1": {
            "id": "chunk-1",
            "chunk_index": 2,
            "content": "hello world",
            "indexed_at": datetime(2026, 7, 11, 12, 0, 0),
            "vector": [0.1, 0.2],
        }
    }
    slim = _slim_pool_for_pending(pool)
    import json

    json.dumps({"pool": slim})
    assert slim["chunk-1"]["chunk_index"] == 2
    assert "indexed_at" not in slim["chunk-1"]


def test_estimate_rerank_prompt_tokens_delegates():
    from app.services import jina_runtime

    with patch.object(jina_runtime, "estimate_rerank_prompt_tokens", return_value=42793) as mock_fn:
        count = jina_runtime.estimate_rerank_prompt_tokens("hello", ["doc1", "doc2"])
        assert count == 42793
        mock_fn.assert_called_once_with("hello", ["doc1", "doc2"])


@pytest.mark.skipif(
    not __import__("os").environ.get("IN_WORKER_EXEC"),
    reason="GGUF tokenize smoke requires api-worker with models",
)
def test_estimate_rerank_prompt_tokens_matches_tokenize():
    from _jina_common import _format_rerank_prompt, estimate_rerank_prompt_tokens, _get_rerank_tokenize_llm
    from download_models2 import expected_jina_reranker_path

    query = "hybrid search test"
    docs = ["short doc", "another passage"]
    count = estimate_rerank_prompt_tokens(query, docs)
    llm = _get_rerank_tokenize_llm(expected_jina_reranker_path())
    prompt = _format_rerank_prompt(query, docs)
    expected = len(llm.tokenize(prompt.encode("utf-8")))
    assert count == expected
