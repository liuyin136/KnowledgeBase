"""Tests for Phase 2 graph-memory Neo4j client helpers."""
from __future__ import annotations

from unittest.mock import patch

from app.services.neo4j_client import Neo4jClient


def test_delete_memory_subgraph_targets_memory_key_only():
    client = Neo4jClient.__new__(Neo4jClient)
    with (
        patch.object(
            client,
            "_run_read",
            return_value=[{"label": "Entity", "cnt": 2}],
        ),
        patch.object(client, "_run_write", return_value=[]) as mock_write,
    ):
        stats = client.delete_memory_subgraph("abc123")

    assert stats["Entity"] == 2
    assert mock_write.call_count == 2
    delete_cypher = mock_write.call_args_list[0][0][0]
    assert "memory_key" in delete_cypher
    assert "Knowledgechunk_grand" not in delete_cypher


def test_merge_memory_graph_calls_delete_first():
    client = Neo4jClient.__new__(Neo4jClient)
    with (
        patch.object(client, "get_memory_version", return_value=1),
        patch.object(client, "delete_memory_subgraph", return_value={}) as mock_delete,
        patch.object(client, "_run_write", return_value=[{"memory_id": "m1", "version": 2}]),
    ):
        result = client.merge_memory_graph(
            memory_key="k1",
            memory_id="m1",
            query_text="q",
            user_query_id="uq1",
            trace_id="span",
            summary="summary",
            grandchild_ids=["g1"],
            entities=[{"entity_id": "e1", "name": "Ada", "type": "person", "grandchild_id": "g1"}],
            relations=[],
            claims=[{"claim_id": "c1", "text": "fact", "entity_id": "e1", "confidence": 0.9, "grandchild_id": "g1"}],
            communities=[{"community_id": "c0", "level": 0, "entity_ids": ["e1"]}],
            summaries=[{"summary_id": "c0_l0", "community_id": "c0", "level": 0, "text": "sum"}],
        )

    mock_delete.assert_called_once_with("k1")
    assert result["version"] == 2
    assert result["entities_created"] == 1


def test_get_grandchild_contents_preserves_order():
    client = Neo4jClient.__new__(Neo4jClient)
    with patch.object(
        client,
        "_run_read",
        return_value=[
            {"id": "g2", "content": "b", "source_file": "a.md"},
            {"id": "g1", "content": "a", "source_file": "a.md"},
        ],
    ):
        rows = client.get_grandchild_contents(["g1", "g2"])

    assert [r["id"] for r in rows] == ["g1", "g2"]
