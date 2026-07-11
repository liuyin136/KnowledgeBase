from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services import retrieval_memory


def test_retrieval_tree_roundtrip():
    with patch("app.services.retrieval_memory.get_redis_connection") as mock_conn:
        store: dict[str, str] = {}

        def setex(key, ttl, value):
            store[key] = value

        def get(key):
            return store.get(key)

        redis_mock = MagicMock()
        redis_mock.setex.side_effect = setex
        redis_mock.get.side_effect = get
        mock_conn.return_value = redis_mock

        payload = retrieval_memory.save_retrieval_tree(
            "session-1",
            parent_ids=["p1", "p1"],
            child_ids=["c1", "c2"],
            grandchild_ids=["g1"],
            span_id="span-x",
            query="hello world",
        )
        assert payload["retrieval_tree"]["parent_ids"] == ["p1"]
        assert payload["retrieval_tree"]["child_ids"] == ["c1", "c2"]
        assert payload["query_hash"]

        loaded = retrieval_memory.load_retrieval_tree("session-1")
        assert loaded is not None
        assert loaded["retrieval_tree"]["grandchild_ids"] == ["g1"]
