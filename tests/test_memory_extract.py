"""Tests for memory_key + extract_memory_graph worker (mocked)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.memory_key import compute_memory_key
from app.workers import tasks


def test_compute_memory_key_stable():
    k1 = compute_memory_key("uq", ["b", "a"])
    k2 = compute_memory_key("uq", ["a", "b"])
    assert k1 == k2
    assert len(k1) == 64


def test_extract_memory_graph_lww_increments_version():
    graph = MagicMock()
    graph.summary = "s"
    graph.entities = [MagicMock(entity_id="e1", name="Ada", type="person")]
    graph.relations = []
    graph.claims = [MagicMock(claim_id="c1", text="t", entity_id="e1", confidence=0.8, grandchild_id=None)]

    with (
        patch("app.workers.tasks.get_neo4j_client") as mock_client_fn,
        patch("app.services.liquid_runtime.load_extract_model", return_value=MagicMock()),
        patch("app.services.liquid_runtime.release_extract_model"),
        patch("app.services.liquid_extract.extract_graph_from_chunks", return_value=graph),
        patch("app.services.graph_community.partition_entities", return_value=[]),
        patch("app.services.graph_community.build_community_summaries", return_value=[]),
        patch("app.workers.tasks.push_metrics"),
    ):
        client = MagicMock()
        client.get_memory_version.return_value = 1
        client.get_grandchild_contents.return_value = [{"id": "g1", "content": "text", "source_file": "a.md"}]
        client.merge_memory_graph.return_value = {
            "memory_id": "m1",
            "memory_key": "k",
            "version": 2,
            "entities_created": 1,
            "relations_created": 0,
            "claims_created": 1,
            "communities_created": 0,
            "summaries_created": 0,
        }
        mock_client_fn.return_value = client

        result = tasks.extract_memory_graph("query", ["g1"], user_query_id="uq1")

    assert result["version"] == 2
    client.merge_memory_graph.assert_called_once()
