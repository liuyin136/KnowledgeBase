"""Tests for blocked _benchmark/ ingest paths."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.exceptions import IngestBlockedError
from app.main import app
from app.models.neo4j_models import Knowledge
from app.services.ingest_guard import assert_ingestible_source


def test_assert_ingestible_source_rejects_benchmark() -> None:
    with pytest.raises(IngestBlockedError):
        assert_ingestible_source("_benchmark/hybrid_fixture/chunk-1.md")


def test_assert_ingestible_source_allows_benchmark_with_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALLOW_BENCHMARK_INGEST", "1")
    assert_ingestible_source("_benchmark/hybrid_fixture/chunk-1.md")


def test_ingest_document_rejects_benchmark() -> None:
    from app.workers.tasks import ingest_document

    with patch("app.workers.health.run_health_checks"):
        with pytest.raises(IngestBlockedError):
            ingest_document("_benchmark/hybrid_fixture/x.md")


def test_ingest_document_allows_benchmark_with_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.workers.tasks import ingest_document

    monkeypatch.setenv("ALLOW_BENCHMARK_INGEST", "1")
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    rel = "_benchmark/hybrid_fixture/x.md"
    full = tmp_path / rel
    full.parent.mkdir(parents=True)
    full.write_text("hello world", encoding="utf-8")

    with (
        patch("app.workers.health.run_health_checks"),
        patch("app.workers.tasks.push_metrics"),
        patch("app.workers.tasks.set_indexed"),
        patch("app.workers.tasks.jina_runtime.load_retrieval_model") as load_llm,
        patch("app.workers.tasks.chunk_document", return_value=[]),
        patch("app.workers.tasks.get_neo4j_client") as get_client,
        patch("app.workers.tasks.jina_runtime.release_model"),
    ):
        get_client.return_value.get_existing_chunks.return_value = {}
        get_client.return_value.get_knowledge_by_source.return_value = None
        get_client.return_value.upsert_knowledge.return_value = {
            "chunks_written": 0,
            "chunks_skipped": 0,
            "chunks_updated": 0,
            "deleted_orphans": 0,
        }
        load_llm.return_value = object()
        with patch(
            "app.workers.tasks.jina_runtime.tokenizers_from_llm",
            return_value=(lambda x: [], lambda x: ""),
        ):
            ingest_document(rel)


def test_upsert_knowledge_rejects_benchmark() -> None:
    from app.services.neo4j_client import Neo4jClient

    client = Neo4jClient(uri="bolt://localhost:7687", user="neo4j", password="x")
    knowledge = Knowledge(
        id="k1",
        source_file="_benchmark/hybrid_fixture/x.md",
        title="x",
        category="_benchmark",
    )
    with pytest.raises(IngestBlockedError):
        client.upsert_knowledge(knowledge, [], link_log_file=False)
    client.close()


@pytest.fixture()
def files_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    settings = Settings(data_root=str(tmp_path))
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)
    monkeypatch.setattr("app.services.file_store.get_settings", lambda: settings)
    get_settings.cache_clear()
    return TestClient(app)


def test_files_reindex_returns_400(files_client: TestClient) -> None:
    res = files_client.post("/api/v1/files/_benchmark/hybrid_fixture/x.md/reindex")
    assert res.status_code == 400
    assert "blocked" in res.json()["detail"].lower()
