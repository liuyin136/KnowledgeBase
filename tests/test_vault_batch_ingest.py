"""Tests for batch ingest endpoint (Phase 1.7)."""
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


def test_batch_ingest_queues_per_file(client: TestClient) -> None:
    folder = client.post("/api/v1/rag/vault/folders", json={"name": "Batch"}).json()
    a = client.post(
        "/api/v1/rag/vault/files",
        json={"folder_id": folder["id"], "filename": "a.md", "content": "a"},
    ).json()["file"]
    b = client.post(
        "/api/v1/rag/vault/files",
        json={"folder_id": folder["id"], "filename": "b.md", "content": "b"},
    ).json()["file"]

    with patch("app.routers.vault.enqueue_vault_ingest", side_effect=["job-a", "job-b"]) as mock_enqueue:
        res = client.post(
            "/api/v1/rag/vault/files/batch-ingest",
            json={"file_ids": [a["id"], b["id"]]},
        )

    assert res.status_code == 202
    body = res.json()
    assert set(body["queued"]) == {a["id"], b["id"]}
    assert body["skipped"] == []
    assert mock_enqueue.call_count == 2


def test_batch_ingest_skips_locked(client: TestClient) -> None:
    folder = client.post("/api/v1/rag/vault/folders", json={"name": "Lock"}).json()
    a = client.post(
        "/api/v1/rag/vault/files",
        json={"folder_id": folder["id"], "filename": "a.md", "content": "a"},
    ).json()["file"]
    b = client.post(
        "/api/v1/rag/vault/files",
        json={"folder_id": folder["id"], "filename": "b.md", "content": "b"},
    ).json()["file"]
    vault_db.update_file_fields(b["id"], ingest_lock_job_id="busy", index_status="pending")

    with patch("app.routers.vault.enqueue_vault_ingest", return_value="job-a"):
        res = client.post(
            "/api/v1/rag/vault/files/batch-ingest",
            json={"file_ids": [a["id"], b["id"]]},
        )

    assert res.status_code == 202
    body = res.json()
    assert body["queued"] == [a["id"]]
    assert len(body["skipped"]) == 1
    assert body["skipped"][0]["file_id"] == b["id"]
