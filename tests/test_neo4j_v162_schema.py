"""Tests for Phase 1.62 Neo4j schema helpers (mock driver, no GPU)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.core.constants import (
    FAMILY_COARSE_INDEX_NAMES,
    GRANDCHILD_COARSE_INDEX_NAMES,
    PARENT_COARSE_INDEX_NAMES,
)
from app.services.neo4j_client import Neo4jClient


def test_delete_all_ingestion_includes_family_label():
    client = Neo4jClient.__new__(Neo4jClient)
    with (
        patch.object(client, "_run_read", return_value=[]) as mock_read,
        patch.object(client, "_run_write", return_value=[]),
    ):
        client.delete_all_ingestion()
    cypher = mock_read.call_args[0][0]
    assert ":Knowledgechunk_family" in cypher
    assert ":Knowledgechunk_grand" in cypher


def test_delete_knowledge_tree_includes_family():
    client = Neo4jClient.__new__(Neo4jClient)
    with patch.object(
        client,
        "_run_write",
        return_value=[
            {
                "grandchildren_deleted": 1,
                "children_deleted": 2,
                "parents_deleted": 1,
                "families_deleted": 1,
            }
        ],
    ) as mock_write:
        stats = client.delete_knowledge_tree_for_source("news/a.md")
    cypher = mock_write.call_args[0][0]
    assert "HAS_FAMILY" in cypher
    assert "Knowledgechunk_family" in cypher
    assert stats["families_deleted"] == 1


def test_upsert_knowledge_tree_v162_writes_family_label():
    from app.models.neo4j_models import (
        Knowledge,
        KnowledgeChild,
        KnowledgeFamily,
        KnowledgeGrandchild,
        KnowledgeParent,
    )

    client = Neo4jClient.__new__(Neo4jClient)
    writes: list[str] = []

    def capture_write(cypher: str, params: dict):
        writes.append(cypher)
        return [{"id": params.get("id")}]

    with (
        patch.object(client, "delete_knowledge_tree_for_source", return_value={}),
        patch.object(client, "delete_legacy_chunks_for_source", return_value=0),
        patch.object(client, "_run_write", side_effect=capture_write),
        patch("app.services.neo4j_client.assert_ingestible_source"),
    ):
        knowledge = Knowledge(id="k1", source_file="news/a.md", title="a", category="news")
        family = KnowledgeFamily(
            id="f1",
            family_index=0,
            content="body",
            content_hash="h",
            source_file="news/a.md",
            token_count=1,
            vector=[0.1],
            vector_coarse_256=[0.1],
            vector_coarse_512=[0.1],
        )
        parent = KnowledgeParent(
            id="p1",
            parent_index=0,
            content="# H",
            content_hash="h",
            header_path="H",
            source_file="news/a.md",
            token_count=1,
            family_id="f1",
            vector=[0.1],
            vector_coarse_256=[0.1],
            vector_coarse_512=[0.1],
        )
        child = KnowledgeChild(
            id="c1",
            parent_id="p1",
            child_index=0,
            content="para",
            content_hash="h",
            token_count=1,
            source_file="news/a.md",
            vector=[0.1],
            vector_coarse_256=[0.1],
            vector_coarse_512=[0.1],
        )
        gc = KnowledgeGrandchild(
            id="g1",
            child_id="c1",
            parent_id="p1",
            grandchild_index=0,
            content="sent",
            source_file="news/a.md",
            content_hash="h",
            token_count=1,
            vector=[0.1],
            vector_coarse_256=[0.1],
            vector_coarse_512=[0.1],
        )
        stats = client.upsert_knowledge_tree_v162(
            knowledge, [family], [parent], [child], [gc], link_log_file=False
        )

    joined = "\n".join(writes)
    assert "Knowledgechunk_family" in joined
    assert "HAS_FAMILY" in joined
    assert "vector_coarse_256" in joined
    assert stats["families_written"] == 1
    assert stats["grandchildren_written"] == 1


def test_family_vector_index_names_match_ddl():
    assert "family" in FAMILY_COARSE_INDEX_NAMES[256]
    assert "parent" in PARENT_COARSE_INDEX_NAMES[256]
    assert "grand" in GRANDCHILD_COARSE_INDEX_NAMES[256]


def test_vector_search_family_uses_family_index():
    client = Neo4jClient.__new__(Neo4jClient)
    client._log_query = MagicMock()
    with patch.object(client, "_run_read", return_value=[]) as mock_read:
        client.vector_search_coarse_family(256, [0.1] * 256, 10)
    cypher = mock_read.call_args[0][0]
    assert FAMILY_COARSE_INDEX_NAMES[256] in cypher
    assert "Knowledgechunk_family" in cypher
