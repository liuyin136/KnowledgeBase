"""Batch delete / upload tests for vault API."""
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


def test_batch_delete_partial_lock(client: TestClient) -> None:
    folder = client.post("/api/v1/rag/vault/folders", json={"name": "News"}).json()
    with patch("app.routers.vault.enqueue_vault_ingest", return_value="job-x"):
        a = client.post(
            "/api/v1/rag/vault/files",
            json={"folder_id": folder["id"], "filename": "a.md", "content": "a"},
        ).json()["file"]
        b = client.post(
            "/api/v1/rag/vault/files",
            json={"folder_id": folder["id"], "filename": "b.md", "content": "b"},
        ).json()["file"]

    vault_db.update_file_fields(b["id"], ingest_lock_job_id="lock-1", index_status="pending")

    with patch("app.services.neo4j_client.get_neo4j_client") as mock_get:
        mock_get.return_value.delete_knowledge_by_source.return_value = 0
        res = client.request(
            "DELETE",
            "/api/v1/rag/vault/files/batch",
            json={"file_ids": [a["id"], b["id"]]},
        )

    assert res.status_code == 200
    results = {r["file_id"]: r for r in res.json()["results"]}
    assert results[a["id"]]["ok"] is True
    assert results[b["id"]]["ok"] is False
    assert results[b["id"]]["error"]
