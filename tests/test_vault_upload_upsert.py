"""Tests for vault upload upsert (same-name replace) behavior."""
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


def test_upload_same_name_replaces_without_ingest(client: TestClient) -> None:
    folder = client.post("/api/v1/rag/vault/folders", json={"name": "Docs"}).json()
    with patch("app.routers.vault.enqueue_vault_ingest") as mock_ingest:
        first = client.post(
            "/api/v1/rag/vault/files",
            json={"folder_id": folder["id"], "filename": "a.md", "content": "v1"},
        )
        assert first.status_code == 201
        assert first.json()["replaced"] is False
        file_id = first.json()["file"]["id"]

        second = client.post(
            "/api/v1/rag/vault/files",
            json={"folder_id": folder["id"], "filename": "a.md", "content": "v2"},
        )
        assert second.status_code == 201
        body = second.json()
        assert body["replaced"] is True
        assert body["file"]["id"] == file_id
        assert body["ingest_job_id"] is None

    mock_ingest.assert_not_called()
    content = client.get(f"/api/v1/rag/vault/files/{file_id}/content")
    assert content.json()["content"] == "v2"


def test_upload_after_soft_delete_resurrects(client: TestClient) -> None:
    from app.core.config import get_settings

    folder = client.post("/api/v1/rag/vault/folders", json={"name": "News"}).json()
    first = client.post(
        "/api/v1/rag/vault/files",
        json={"folder_id": folder["id"], "filename": "revive.md", "content": "old"},
    )
    assert first.status_code == 201
    file_id = first.json()["file"]["id"]

    settings = get_settings()
    path = Path(settings.vault_root) / "news" / "revive.md"
    assert path.is_file()
    path.unlink()

    with patch("app.services.vault_sync._purge_neo4j"):
        from app.services.vault_sync import sync_vault

        sync_vault()

    row = vault_db.get_file_by_id(file_id)
    assert row is not None
    assert row["index_status"] == "deleted"

    res = client.post(
        "/api/v1/rag/vault/files",
        json={
            "folder_id": folder["id"],
            "filename": "revive.md",
            "content": "new body",
        },
    )
    assert res.status_code == 201
    body = res.json()
    assert body["replaced"] is True
    assert body["file"]["id"] == file_id
    assert body["file"]["index_status"] == "not_indexed"


def test_upload_locked_file_409(client: TestClient) -> None:
    folder = client.post("/api/v1/rag/vault/folders", json={"name": "Lock"}).json()
    first = client.post(
        "/api/v1/rag/vault/files",
        json={"folder_id": folder["id"], "filename": "x.md", "content": "a"},
    )
    file_id = first.json()["file"]["id"]
    vault_db.update_file_fields(file_id, ingest_lock_job_id="busy-job")

    res = client.post(
        "/api/v1/rag/vault/files",
        json={"folder_id": folder["id"], "filename": "x.md", "content": "b"},
    )
    assert res.status_code == 409


def test_on_conflict_fail_returns_409(client: TestClient) -> None:
    folder = client.post("/api/v1/rag/vault/folders", json={"name": "Fail"}).json()
    client.post(
        "/api/v1/rag/vault/files",
        json={"folder_id": folder["id"], "filename": "dup.md", "content": "1"},
    )
    res = client.post(
        "/api/v1/rag/vault/files?on_conflict=fail",
        json={"folder_id": folder["id"], "filename": "dup.md", "content": "2"},
    )
    assert res.status_code == 409


def test_batch_upload_reports_replaced_and_failed(client: TestClient) -> None:
    folder = client.post("/api/v1/rag/vault/folders", json={"name": "Batch"}).json()
    client.post(
        "/api/v1/rag/vault/files",
        json={"folder_id": folder["id"], "filename": "exist.md", "content": "old"},
    )

    files = [
        ("files", ("exist.md", b"new", "text/markdown")),
        ("files", ("fresh.md", b"hello", "text/markdown")),
    ]
    res = client.post(
        "/api/v1/rag/vault/files/batch-upload",
        data={"folder_id": folder["id"]},
        files=files,
    )
    assert res.status_code == 201
    results = {f["filename"]: f for f in res.json()["files"]}
    assert results["exist.md"]["status"] == "replaced"
    assert results["exist.md"]["job_id"] is None
    assert results["fresh.md"]["status"] == "uploaded"
    assert results["fresh.md"]["job_id"] is None


def test_list_files_includes_content_preview(client: TestClient) -> None:
    folder = client.post("/api/v1/rag/vault/folders", json={"name": "Prev"}).json()
    long_text = "# Title\n\n" + ("word " * 80)
    client.post(
        "/api/v1/rag/vault/files",
        json={
            "folder_id": folder["id"],
            "filename": "long.md",
            "content": long_text,
        },
    )
    listed = client.get("/api/v1/rag/vault/files")
    assert listed.status_code == 200
    file_row = listed.json()["files"][0]
    assert file_row["content_preview"]
    assert len(file_row["content_preview"]) <= 241
