"""Tests for ingest token preview (Phase 1.7)."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app
from app.services import vault_db
from app.services.ingest_estimate import estimate_tokens_from_text


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


def test_estimate_tokens_from_text_positive() -> None:
    tokens = estimate_tokens_from_text("# Hello\n\nSome paragraph text here.")
    assert tokens > 0


def test_ingest_preview_returns_tokens(client: TestClient) -> None:
    folder = client.post("/api/v1/rag/vault/folders", json={"name": "Docs"}).json()
    created = client.post(
        "/api/v1/rag/vault/files",
        json={
            "folder_id": folder["id"],
            "filename": "a.md",
            "content": "# Title\n\nBody text for ingest estimate.",
        },
    ).json()
    file_id = created["file"]["id"]

    res = client.post(
        "/api/v1/rag/vault/files/ingest-preview",
        json={"file_ids": [file_id]},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["file_count"] == 1
    assert body["total_estimated_tokens"] > 0
    assert body["items"][0]["ingestible"] is True
