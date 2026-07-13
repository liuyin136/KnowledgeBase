"""Tests for complete Neo4j ingestion purge helpers (Phase 1.61)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.neo4j_client import Neo4jClient


def test_delete_ingestion_tree_for_source_calls_v16_legacy_knowledge_logfile():
    client = Neo4jClient.__new__(Neo4jClient)
    with (
        patch.object(
            client,
            "delete_knowledge_tree_for_source",
            return_value={"parents_deleted": 2, "children_deleted": 5, "grandchildren_deleted": 10},
        ) as mock_tree,
        patch.object(client, "delete_legacy_chunks_for_source", return_value=3) as mock_legacy,
        patch.object(client, "_run_write", side_effect=[[{"deleted": 1}], [{"deleted": 1}]]) as mock_write,
    ):
        stats = client.delete_ingestion_tree_for_source("news/a.md")

    mock_tree.assert_called_once_with("news/a.md")
    mock_legacy.assert_called_once_with("news/a.md")
    assert mock_write.call_count == 2
    knowledge_cypher = mock_write.call_args_list[0][0][0]
    logfile_cypher = mock_write.call_args_list[1][0][0]
    assert ":Knowledge {source_file:" in knowledge_cypher
    assert ":LogFile {path:" in logfile_cypher
    assert stats["parents_deleted"] == 2
    assert stats["legacy_chunks_deleted"] == 3
    assert stats["knowledge_deleted"] == 1
    assert stats["logfile_deleted"] == 1


def test_delete_all_vault_ingestion_loops_sources_and_benchmark():
    client = Neo4jClient.__new__(Neo4jClient)
    with (
        patch.object(
            client,
            "delete_ingestion_tree_for_source",
            return_value={"parents_deleted": 1, "children_deleted": 1, "grandchildren_deleted": 1,
                          "legacy_chunks_deleted": 0, "knowledge_deleted": 1, "logfile_deleted": 1},
        ) as mock_per_source,
        patch.object(
            client,
            "delete_knowledge_by_prefix",
            return_value={"knowledge_deleted": 2, "chunks_deleted": 4},
        ) as mock_bench,
    ):
        stats = client.delete_all_vault_ingestion(["news/a.md", "docs/b.md"])

    assert mock_per_source.call_count == 2
    mock_bench.assert_called_once_with("_benchmark/")
    assert stats["parents_deleted"] == 2
    assert stats["benchmark_knowledge_deleted"] == 2


def test_delete_all_ingestion_includes_v16_and_logfile_labels():
    client = Neo4jClient.__new__(Neo4jClient)
    count_rows = [
        {"label": "Knowledgechunk", "cnt": 3},
        {"label": "Knowledgechunk_sen", "cnt": 12},
        {"label": "Knowledgechunk_grand", "cnt": 40},
        {"label": "LogFile", "cnt": 2},
    ]
    with (
        patch.object(client, "_run_read", return_value=count_rows) as mock_read,
        patch.object(client, "_run_write", return_value=[]) as mock_write,
    ):
        stats = client.delete_all_ingestion()

    read_cypher = mock_read.call_args[0][0]
    write_cypher = mock_write.call_args[0][0]
    for label in (
        "Knowledgechunk_grand",
        "Knowledgechunk_sen",
        "Knowledgechunk",
        "KnowledgeChunk",
        "Knowledge",
        "LogFile",
    ):
        assert f":{label}" in read_cypher
        assert f":{label}" in write_cypher
    assert stats["Knowledgechunk_sen"] == 12
    assert stats["LogFile"] == 2


def test_delete_all_knowledge_delegates_to_delete_all_ingestion():
    client = Neo4jClient.__new__(Neo4jClient)
    with patch.object(
        client,
        "delete_all_ingestion",
        return_value={"Knowledge": 5, "KnowledgeChunk": 20, "Knowledgechunk_sen": 100},
    ):
        stats = client.delete_all_knowledge()
    assert stats == {"knowledge_deleted": 5, "chunks_deleted": 20}
