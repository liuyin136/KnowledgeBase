"""Tests for clear-index endpoint (Phase 1.7)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
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


def test_clear_index_indexed_only(client: TestClient) -> None:
    folder = client.post("/api/v1/rag/vault/folders", json={"name": "Docs"}).json()
    created = client.post(
        "/api/v1/rag/vault/files",
        json={"folder_id": folder["id"], "filename": "a.md", "content": "hi"},
    ).json()
    file_id = created["file"]["id"]
    vault_db.update_file_status(file_id, index_status="indexed", chunk_count=3)

    with patch("app.services.neo4j_client.get_neo4j_client") as mock_get:
        mock_get.return_value.delete_ingestion_tree_for_source.return_value = {
            "grandchildren_deleted": 1,
            "knowledge_deleted": 1,
        }
        res = client.post(f"/api/v1/rag/vault/files/{file_id}/clear-index")

    assert res.status_code == 200
    body = res.json()
    assert body["index_status"] == "not_indexed"
    row = vault_db.get_file_by_id(file_id)
    assert row is not None
    assert row["index_status"] == "not_indexed"
    assert row["chunk_count"] == 0
    mock_get.return_value.delete_ingestion_tree_for_source.assert_called_once()


def test_clear_index_409_on_not_indexed(client: TestClient) -> None:
    folder = client.post("/api/v1/rag/vault/folders", json={"name": "Docs"}).json()
    created = client.post(
        "/api/v1/rag/vault/files",
        json={"folder_id": folder["id"], "filename": "b.md", "content": "hi"},
    ).json()
    file_id = created["file"]["id"]
    assert created["file"]["index_status"] == "not_indexed"

    res = client.post(f"/api/v1/rag/vault/files/{file_id}/clear-index")
    assert res.status_code == 409
