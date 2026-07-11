"""Tests for Neo4j path-filtered recall."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.neo4j_client import Neo4jClient


def test_vector_search_returns_empty_for_empty_allowlist():
    client = Neo4jClient.__new__(Neo4jClient)
    assert client.vector_search_coarse_chunks(256, [0.1] * 256, 50, allowed_paths=[]) == []


def test_bm25_search_returns_empty_for_empty_allowlist():
    client = Neo4jClient.__new__(Neo4jClient)
    assert client.bm25_search_chunks("query", 50, allowed_paths=[]) == []


def test_vector_search_passes_allowed_paths_to_cypher():
    client = Neo4jClient.__new__(Neo4jClient)
    client._log_query = MagicMock()
    with patch.object(client, "_run_read", return_value=[]) as mock_read:
        client.vector_search_coarse_chunks(
            256,
            [0.1] * 256,
            50,
            allowed_paths=["news/a.md"],
        )
    mock_read.assert_called_once()
    _cypher, params = mock_read.call_args[0]
    assert "IN $allowed_paths" in _cypher
    assert params["allowed_paths"] == ["news/a.md"]


def test_bm25_search_omits_path_filter_when_unscoped():
    client = Neo4jClient.__new__(Neo4jClient)
    client._log_query = MagicMock()
    with patch.object(client, "_run_read", return_value=[]) as mock_read:
        client.bm25_search_chunks("query", 50, allowed_paths=None)
    _cypher, params = mock_read.call_args[0]
    assert "IN $allowed_paths" not in _cypher
    assert "allowed_paths" not in params
