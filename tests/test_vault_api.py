"""API tests for RAG Content Vault."""
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


def test_create_folder_and_list(client: TestClient) -> None:
    res = client.post("/api/v1/rag/vault/folders", json={"name": "News"})
    assert res.status_code == 201
    folder = res.json()
    assert folder["slug"] == "news"

    listed = client.get("/api/v1/rag/vault/folders")
    assert listed.status_code == 200
    assert len(listed.json()["folders"]) == 1


def test_delete_nonempty_folder_409(client: TestClient) -> None:
    folder = client.post("/api/v1/rag/vault/folders", json={"name": "News"}).json()
    with patch("app.routers.vault.enqueue_vault_ingest", return_value="job-1"):
        created = client.post(
            "/api/v1/rag/vault/files",
            json={"folder_id": folder["id"], "filename": "a.md", "content": "hi"},
        )
    assert created.status_code == 201

    res = client.delete(f"/api/v1/rag/vault/folders/{folder['id']}")
    assert res.status_code == 409


def test_pagination(client: TestClient) -> None:
    folder = client.post("/api/v1/rag/vault/folders", json={"name": "News"}).json()
    with patch("app.routers.vault.enqueue_vault_ingest", return_value="job-x"):
        for i in range(12):
            client.post(
                "/api/v1/rag/vault/files",
                json={
                    "folder_id": folder["id"],
                    "filename": f"a{i}.md",
                    "content": f"c{i}",
                },
            )

    page1 = client.get("/api/v1/rag/vault/files?page=1&page_size=10")
    assert page1.status_code == 200
    data = page1.json()
    assert data["total"] == 12
    assert len(data["files"]) == 10
    assert data["total_pages"] == 2

    bad = client.get("/api/v1/rag/vault/files?page_size=7")
    assert bad.status_code == 422


def test_lock_blocks_edit(client: TestClient) -> None:
    folder = client.post("/api/v1/rag/vault/folders", json={"name": "News"}).json()
    with patch("app.routers.vault.enqueue_vault_ingest", return_value="job-1"):
        created = client.post(
            "/api/v1/rag/vault/files",
            json={"folder_id": folder["id"], "filename": "a.md", "content": "hi"},
        ).json()
    file_id = created["file"]["id"]
    vault_db.update_file_fields(file_id, ingest_lock_job_id="job-1", index_status="pending")

    res = client.put(
        f"/api/v1/rag/vault/files/{file_id}/content",
        json={"content": "new"},
    )
    assert res.status_code == 409


def test_sync_endpoint(client: TestClient) -> None:
    res = client.post("/api/v1/rag/vault/sync")
    assert res.status_code == 200
    body = res.json()
    assert "files_scanned" in body
    assert "drift_added" in body
