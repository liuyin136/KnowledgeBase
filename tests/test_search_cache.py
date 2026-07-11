from __future__ import annotations

import json

import pytest

from app.services import search_cache
from app.services.ingest_status import get_status, resolve_index_status, set_pending, set_indexed


def test_cache_key_differs_by_coarse_dim():
    k256 = search_cache.cache_key(
        query="test",
        w1=0.7,
        w2=0.3,
        recall_k=50,
        rerank_k=10,
        coarse_dim=256,
        use_minmax_fallback=False,
    )
    k512 = search_cache.cache_key(
        query="test",
        w1=0.7,
        w2=0.3,
        recall_k=50,
        rerank_k=10,
        coarse_dim=512,
        use_minmax_fallback=False,
    )
    assert k256 != k512


def test_cache_key_differs_by_folder_ids():
    base = dict(
        query="test",
        w1=0.7,
        w2=0.3,
        recall_k=50,
        rerank_k=10,
        coarse_dim=256,
        use_minmax_fallback=False,
    )
    k1 = search_cache.cache_key(**base, folder_ids=["a"])
    k2 = search_cache.cache_key(**base, folder_ids=["b"])
    assert k1 != k2


def test_ingest_status_pending_then_indexed(redis_client):
    path = "RND/test.md"
    set_pending(path, "job-123")
    pending = get_status(path)
    assert pending is not None
    assert pending["index_status"] == "pending"
    assert pending["last_ingest_job_id"] == "job-123"

    meta = resolve_index_status(path, neo4j_knowledge=None)
    assert meta["index_status"] == "pending"

    set_indexed(path, "job-123", chunk_count=3)
    indexed = get_status(path)
    assert indexed["index_status"] == "indexed"
    assert indexed["chunk_count"] == 3


@pytest.fixture
def redis_client(monkeypatch):
    store: dict[str, str] = {}

    class FakeRedis:
        def setex(self, key, ttl, value):
            store[key] = value

        def get(self, key):
            return store.get(key)

    fake = FakeRedis()
    monkeypatch.setattr("app.services.ingest_status._redis", lambda: fake)
    monkeypatch.setattr("app.services.search_cache._redis", lambda: fake)
    return fake


def test_search_cache_roundtrip(redis_client):
    key = search_cache.cache_key(
        query="hello",
        w1=0.7,
        w2=0.3,
        recall_k=50,
        rerank_k=10,
        coarse_dim=256,
        use_minmax_fallback=False,
    )
    payload = {"hits": [], "fusion_meta": {"pool_size": 0}, "span_id": "abc"}
    search_cache.set_cached(key, payload)
    cached = search_cache.get_cached(key)
    assert cached == payload
