"""Tests for Redis episodic session store."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services import episodic_memory


def test_save_and_load_episodic_session():
    store: dict[str, str] = {}

    conn = MagicMock()

    def _setex(key, ttl, value):
        store[key] = value

    def _get(key):
        return store.get(key)

    conn.setex.side_effect = _setex
    conn.get.side_effect = _get

    with patch("app.services.episodic_memory.get_redis_connection", return_value=conn):
        episodic_memory.save_episodic_session(
            "sess1",
            query="q",
            grandchild_ids=["g1", "g2"],
            memory_key="mk",
            span_id="span",
            retrieval_tree={"grandchild_ids": ["g1"]},
        )
        loaded = episodic_memory.load_episodic_session("sess1")

    assert loaded is not None
    assert loaded["memory_key"] == "mk"
    assert loaded["grandchild_ids"] == ["g1", "g2"]
    assert loaded["retrieval_tree"]["grandchild_ids"] == ["g1"]
