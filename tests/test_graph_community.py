"""Tests for Leiden community partition."""
from __future__ import annotations

from app.models.graph_memory_schemas import ExtractEntity, ExtractRelation
from app.services.graph_community import build_community_summaries, partition_entities


def test_partition_entities_single_component():
    entities = [
        ExtractEntity(entity_id="e1", name="A", type="person"),
        ExtractEntity(entity_id="e2", name="B", type="person"),
    ]
    relations = [ExtractRelation(source_id="e1", target_id="e2", type="knows")]
    communities = partition_entities(entities, relations)
    assert len(communities) >= 1
    assert communities[0].entity_ids


def test_build_community_summaries_without_llm():
    entities = [ExtractEntity(entity_id="e1", name="Ada", type="person")]
    from app.models.graph_memory_schemas import GraphExtractResult

    graph = GraphExtractResult(summary="s", entities=entities, relations=[], claims=[])
    from app.models.graph_memory_schemas import CommunityPartition

    communities = [CommunityPartition(community_id="c0", level=0, entity_ids=["e1"])]
    summaries = build_community_summaries(communities, graph, llm=None)
    assert len(summaries) == 1
    assert "Ada" in summaries[0].text
