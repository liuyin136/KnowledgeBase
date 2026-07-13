"""Leiden community detection + summary helpers for memory subgraphs."""
from __future__ import annotations

from typing import Any

import igraph as ig
import leidenalg

from app.models.graph_memory_schemas import (
    CommunityPartition,
    CommunitySummaryRecord,
    ExtractEntity,
    ExtractRelation,
    GraphExtractResult,
)


def partition_entities(
    entities: list[ExtractEntity],
    relations: list[ExtractRelation],
) -> list[CommunityPartition]:
    if not entities:
        return []

    id_to_idx = {e.entity_id: i for i, e in enumerate(entities)}
    edges: list[tuple[int, int]] = []
    for rel in relations:
        if rel.source_id in id_to_idx and rel.target_id in id_to_idx:
            edges.append((id_to_idx[rel.source_id], id_to_idx[rel.target_id]))

    g = ig.Graph(n=len(entities), edges=edges, directed=False)
    if g.ecount() == 0 and g.vcount() > 1:
        # isolated nodes — single community per connected component of isolates
        partition = CommunityPartition(community_id="c0", level=0, entity_ids=[e.entity_id for e in entities])
        return [partition]

    part = leidenalg.find_partition(g, leidenalg.ModularityVertexPartition)
    buckets: dict[int, list[str]] = {}
    for idx, membership in enumerate(part.membership):
        buckets.setdefault(membership, []).append(entities[idx].entity_id)

    communities: list[CommunityPartition] = []
    for cid, entity_ids in sorted(buckets.items(), key=lambda x: x[0]):
        communities.append(
            CommunityPartition(
                community_id=f"c{cid}",
                level=0,
                entity_ids=entity_ids,
            )
        )
    return communities


def summarize_community_text(
    community: CommunityPartition,
    graph: GraphExtractResult,
    *,
    llm: Any | None = None,
) -> str:
    names = {e.entity_id: e.name for e in graph.entities}
    entity_names = [names.get(eid, eid) for eid in community.entity_ids]
    claim_texts = [
        c.text
        for c in graph.claims
        if c.entity_id in community.entity_ids or not c.entity_id
    ][:5]
    bullet_claims = "; ".join(claim_texts) if claim_texts else graph.summary[:400]

    if llm is None:
        return f"Community {community.community_id}: entities {', '.join(entity_names)}. {bullet_claims}"

    from app.services.extract_llm import run_extract_chat

    prompt = (
        f"Summarize this knowledge community in 2-3 sentences.\n"
        f"Entities: {', '.join(entity_names)}\n"
        f"Claims: {bullet_claims}"
    )
    return run_extract_chat(
        llm,
        [{"role": "user", "content": prompt}],
        max_new_tokens=256,
    ).strip()


def build_community_summaries(
    communities: list[CommunityPartition],
    graph: GraphExtractResult,
    *,
    llm: Any | None = None,
) -> list[CommunitySummaryRecord]:
    summaries: list[CommunitySummaryRecord] = []
    for comm in communities:
        text = summarize_community_text(comm, graph, llm=llm)
        summaries.append(
            CommunitySummaryRecord(
                summary_id=f"{comm.community_id}_l{comm.level}",
                community_id=comm.community_id,
                level=comm.level,
                text=text,
            )
        )

    if len(summaries) > 1 and llm is not None:
        from app.services.extract_llm import run_extract_chat

        rollup = run_extract_chat(
            llm,
            [
                {
                    "role": "user",
                    "content": "Merge these community summaries into one paragraph:\n"
                    + "\n".join(f"- {s.text}" for s in summaries),
                }
            ],
            max_new_tokens=384,
        ).strip()
        summaries.append(
            CommunitySummaryRecord(
                summary_id="l1_global",
                community_id="global",
                level=1,
                text=rollup,
            )
        )
    return summaries
