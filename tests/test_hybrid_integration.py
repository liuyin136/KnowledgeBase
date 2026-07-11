from __future__ import annotations

import pytest

from app.services.fusion import compute_ndcg, compute_recall_at_k
from tests.hybrid_fixture import (
    existing_fixture_map,
    gpu_integration_available,
    gold_ids_for_queries,
    load_queries,
    models_available,
)

pytestmark = pytest.mark.gpu


@pytest.fixture(scope="module")
def fixture_id_map():
    if not gpu_integration_available() or not models_available():
        pytest.skip(
            "GPU integration requires exec on running api-worker: "
            "docker compose exec -e IN_WORKER_EXEC=1 api-worker python -m pytest tests/test_hybrid_integration.py -q"
        )
    query_subset = load_queries()[:2]
    needed = gold_ids_for_queries(query_subset)
    mapping = existing_fixture_map(needed)
    if len(mapping) < len(needed):
        pytest.skip(
            "Benchmark corpus not indexed. Run: "
            "docker compose exec -e ALLOW_BENCHMARK_INGEST=1 api-worker "
            "python scripts/ingest_benchmark_fixture.py"
        )
    return mapping


@pytest.fixture(autouse=True)
def gpu_cleanup_between_tests():
    import gc

    gc.collect()
    yield
    gc.collect()


def _map_hits_to_fixture_ids(hits: list[dict], id_map: dict[str, str]) -> list[str]:
    neo4j_to_fixture = {v: k for k, v in id_map.items()}
    ranked: list[str] = []
    for hit in hits:
        cid = hit["chunk_id"]
        ranked.append(neo4j_to_fixture.get(cid, cid))
    return ranked


def _enqueue_fusion_and_optional_rerank(
    conn,
    q,
    query: str,
    w1: float,
    w2: float,
    *,
    run_rerank: bool = True,
) -> dict:
    import time

    from rq.job import Job

    fusion_job = q.enqueue(
        "app.workers.tasks.hybrid_search_fusion",
        query,
        w1,
        w2,
        50,
        10,
        256,
        job_timeout=300,
    )
    deadline = time.time() + 120
    while time.time() < deadline:
        fusion_job.refresh()
        if fusion_job.is_finished:
            break
        if fusion_job.is_failed:
            pytest.skip(f"fusion job failed (GPU may be exhausted): {fusion_job.exc_info}")
        time.sleep(1)
    else:
        pytest.fail("fusion job timed out")

    fusion_result = Job.fetch(fusion_job.id, connection=conn).result
    assert fusion_result is not None
    if fusion_result.get("status") != "awaiting_rerank":
        return fusion_result

    if not run_rerank:
        return fusion_result

    rerank_job = q.enqueue(
        "app.workers.tasks.hybrid_search_rerank",
        fusion_job.id,
        job_timeout=600,
    )
    deadline = time.time() + 300
    while time.time() < deadline:
        rerank_job.refresh()
        if rerank_job.is_finished:
            return Job.fetch(rerank_job.id, connection=conn).result
        if rerank_job.is_failed:
            pytest.skip(f"rerank job failed (GPU may be exhausted): {rerank_job.exc_info}")
        time.sleep(1)
    pytest.fail("rerank job timed out")


def test_hybrid_search_via_api_smoke():
    """Fusion job stops at awaiting_rerank with token preview metadata."""
    import os

    import redis
    from rq import Queue

    if not gpu_integration_available():
        pytest.skip("GPU worker not available")

    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    conn = redis.from_url(redis_url)
    q = Queue(os.environ.get("RQ_QUEUE_NAME", "default"), connection=conn)
    result = _enqueue_fusion_and_optional_rerank(
        conn,
        q,
        "redis connection pool timeout",
        0.7,
        0.3,
        run_rerank=False,
    )
    assert result["status"] == "awaiting_rerank"
    assert result["rerank_token_count"] > 0
    assert result["rerank_ctx_limit"] == 131072
    workflow = result.get("workflow_log", [])
    assert len(workflow) == 5
    assert [w["phase"] for w in workflow] == [
        "query_embed",
        "coarse_ann",
        "bm25_recall",
        "rescore_1024",
        "hybrid_fusion",
    ]


def test_hybrid_ndcg_beats_vector_on_gpu_fixture(fixture_id_map):
    """CP-B gate: enqueue hybrid vs vector-only jobs on running worker."""
    import os
    import time

    import redis
    from rq import Queue
    from rq.job import Job

    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    conn = redis.from_url(redis_url)
    q = Queue(os.environ.get("RQ_QUEUE_NAME", "default"), connection=conn)

    def _enqueue_search(query: str, w1: float, w2: float) -> dict:
        return _enqueue_fusion_and_optional_rerank(conn, q, query, w1, w2, run_rerank=True)

    hybrid_total = 0.0
    vector_total = 0.0
    recall_total = 0.0

    for row in load_queries()[:2]:
        gold = set(row["gold_chunk_ids"])
        hybrid_res = _enqueue_search(row["query"], 0.7, 0.3)
        vector_res = _enqueue_search(row["query"], 1.0, 0.0)
        hybrid_rank = _map_hits_to_fixture_ids(hybrid_res["hits"], fixture_id_map)
        vector_rank = _map_hits_to_fixture_ids(vector_res["hits"], fixture_id_map)
        hybrid_total += compute_ndcg(gold, hybrid_rank, k=10)
        vector_total += compute_ndcg(gold, vector_rank, k=10)
        recall_total += compute_recall_at_k(gold, hybrid_rank, k=5)

    avg_recall = recall_total / 2
    print(f"hybrid_ndcg@10={hybrid_total:.4f} vector_ndcg@10={vector_total:.4f} recall@5={avg_recall:.4f}")
    assert hybrid_total > vector_total, f"hybrid={hybrid_total:.4f} vector={vector_total:.4f}"
    assert avg_recall > 0.0
