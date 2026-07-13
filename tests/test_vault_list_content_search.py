"""Tests for vault list content keyword search (Phase 1.7)."""
from __future__ import annotations

from pathlib import Path

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


def test_list_files_search_content_matches_body(client: TestClient) -> None:
    folder = client.post("/api/v1/rag/vault/folders", json={"name": "Search"}).json()
    client.post(
        "/api/v1/rag/vault/files",
        json={
            "folder_id": folder["id"],
            "filename": "alpha.md",
            "content": "visible in body UNIQUEPHRASE123",
        },
    )
    client.post(
        "/api/v1/rag/vault/files",
        json={
            "folder_id": folder["id"],
            "filename": "beta.md",
            "content": "nothing special here",
        },
    )

    res = client.get(
        "/api/v1/rag/vault/files",
        params={"keyword": "UNIQUEPHRASE123", "search_content": True},
    )
    assert res.status_code == 200
    files = res.json()["files"]
    assert len(files) == 1
    assert files[0]["filename"] == "alpha.md"


def test_list_files_keyword_matches_relative_path(client: TestClient) -> None:
    folder = client.post("/api/v1/rag/vault/folders", json={"name": "Paths"}).json()
    client.post(
        "/api/v1/rag/vault/files",
        json={"folder_id": folder["id"], "filename": "nested-name.md", "content": "x"},
    )

    res = client.get("/api/v1/rag/vault/files", params={"keyword": "nested-name"})
    assert res.status_code == 200
    assert res.json()["total"] == 1
