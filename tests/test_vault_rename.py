"""Tests for vault folder rename Neo4j consistency."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.exceptions import Neo4jError
from app.main import app
from app.services import vault_db


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    vault_root = tmp_path / "vault"
    db_path = tmp_path / "vault.db"
    vault_root.mkdir(parents=True)
    settings = Settings(
        data_root=str(tmp_path),
        vault_root=str(vault_root),
        vault_db_path=str(db_path),
    )
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)
    monkeypatch.setattr("app.services.vault_db.get_settings", lambda: settings)
    monkeypatch.setattr("app.services.vault_store.get_settings", lambda: settings)
    monkeypatch.setattr("app.services.vault_sync.get_settings", lambda: settings)
    get_settings.cache_clear()
    vault_db.init_vault_db()
    return TestClient(app)


def test_rename_folder_uses_bulk_neo4j_migrate(client: TestClient) -> None:
    news = client.post("/api/v1/rag/vault/folders", json={"name": "News"}).json()
    with patch("app.routers.vault.enqueue_vault_ingest", return_value="job-1"):
        client.post(
            "/api/v1/rag/vault/files",
            json={"folder_id": news["id"], "filename": "a.md", "content": "hi"},
        )

    mock_neo = MagicMock()
    mock_neo.rename_knowledge_by_folder_prefix.return_value = 1
    with patch("app.services.neo4j_client.get_neo4j_client", return_value=mock_neo):
        res = client.patch(f"/api/v1/rag/vault/folders/{news['id']}", json={"name": "Dec"})
    assert res.status_code == 200
    assert res.json()["slug"] == "dec"
    mock_neo.rename_knowledge_by_folder_prefix.assert_called_once_with("news", "dec")


def test_rename_folder_slug_unchanged_skips_neo4j(client: TestClient) -> None:
    folder = client.post("/api/v1/rag/vault/folders", json={"name": "News"}).json()
    mock_neo = MagicMock()
    with patch("app.services.neo4j_client.get_neo4j_client", return_value=mock_neo):
        res = client.patch(
            f"/api/v1/rag/vault/folders/{folder['id']}",
            json={"name": "NEWS"},
        )
    assert res.status_code == 200
    mock_neo.rename_knowledge_by_folder_prefix.assert_not_called()


def test_rename_folder_blocked_when_locked(client: TestClient) -> None:
    folder = client.post("/api/v1/rag/vault/folders", json={"name": "News"}).json()
    with patch("app.routers.vault.enqueue_vault_ingest", return_value="job-1"):
        created = client.post(
            "/api/v1/rag/vault/files",
            json={"folder_id": folder["id"], "filename": "a.md", "content": "hi"},
        ).json()
    file_id = created["file"]["id"]
    vault_db.update_file_fields(file_id, ingest_lock_job_id="job-1", index_status="pending")

    res = client.patch(
        f"/api/v1/rag/vault/folders/{folder['id']}",
        json={"name": "Dec"},
    )
    assert res.status_code == 409


def test_rename_preview_lists_files(client: TestClient) -> None:
    folder = client.post("/api/v1/rag/vault/folders", json={"name": "News"}).json()
    with patch("app.routers.vault.enqueue_vault_ingest", return_value="job-1"):
        for i in range(12):
            client.post(
                "/api/v1/rag/vault/files",
                json={
                    "folder_id": folder["id"],
                    "filename": f"a{i}.md",
                    "content": f"c{i}",
                },
            )

    mock_neo = MagicMock()
    mock_neo.count_knowledge_by_prefix.return_value = 3
    with patch("app.services.neo4j_client.get_neo4j_client", return_value=mock_neo):
        res = client.get(
            f"/api/v1/rag/vault/folders/{folder['id']}/rename-preview",
            params={"name": "Dec"},
        )
    assert res.status_code == 200
    body = res.json()
    assert body["total_files"] == 12
    assert len(body["preview_files"]) == 10
    assert body["has_more_files"] is True
    assert body["neo4j_knowledge_count"] == 3
    assert body["preview_files"][0]["old_relative_path"].startswith("news/")


def test_rename_preview_blocks_when_locked(client: TestClient) -> None:
    folder = client.post("/api/v1/rag/vault/folders", json={"name": "News"}).json()
    with patch("app.routers.vault.enqueue_vault_ingest", return_value="job-1"):
        created = client.post(
            "/api/v1/rag/vault/files",
            json={"folder_id": folder["id"], "filename": "a.md", "content": "hi"},
        ).json()
    vault_db.update_file_fields(
        created["file"]["id"], ingest_lock_job_id="job-1", index_status="pending"
    )

    mock_neo = MagicMock()
    mock_neo.count_knowledge_by_prefix.return_value = 0
    with patch("app.services.neo4j_client.get_neo4j_client", return_value=mock_neo):
        res = client.get(
            f"/api/v1/rag/vault/folders/{folder['id']}/rename-preview",
            params={"name": "Dec"},
        )
    assert res.status_code == 200
    body = res.json()
    assert body["can_rename"] is False
    assert "ingested" in (body["block_reason"] or "").lower()


def test_folder_list_includes_file_count(client: TestClient) -> None:
    folder = client.post("/api/v1/rag/vault/folders", json={"name": "News"}).json()
    with patch("app.routers.vault.enqueue_vault_ingest", return_value="job-1"):
        client.post(
            "/api/v1/rag/vault/files",
            json={"folder_id": folder["id"], "filename": "a.md", "content": "hi"},
        )

    listed = client.get("/api/v1/rag/vault/folders")
    assert listed.status_code == 200
    row = next(f for f in listed.json()["folders"] if f["id"] == folder["id"])
    assert row["file_count"] == 1


def test_neo4j_rename_knowledge_source_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.neo4j_client import Neo4jClient

    client = Neo4jClient(uri="bolt://localhost:7687", user="neo4j", password="x")
    monkeypatch.setattr(
        client,
        "_run_read",
        lambda cypher, params: [{"id": "other-id"}],
    )
    monkeypatch.setattr(
        client,
        "get_knowledge_by_source",
        lambda sf: None,
    )
    with pytest.raises(Neo4jError, match="already exists"):
        client.rename_knowledge_source("news/a.md", "dec/a.md", category="dec")
    client.close()
