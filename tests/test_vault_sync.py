"""Tests for vault sync drift reconciliation."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import Settings, get_settings
from app.services import vault_db, vault_store
from app.services.vault_sync import sync_vault


@pytest.fixture()
def vault_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    vault_root = tmp_path / "vault"
    db_path = tmp_path / "vault.db"
    vault_root.mkdir(parents=True)
    settings = Settings(
        data_root=str(tmp_path),
        vault_root=str(vault_root),
        vault_db_path=str(db_path),
    )

    def _settings() -> Settings:
        return settings

    monkeypatch.setattr("app.core.config.get_settings", _settings)
    monkeypatch.setattr("app.services.vault_db.get_settings", _settings)
    monkeypatch.setattr("app.services.vault_store.get_settings", _settings)
    monkeypatch.setattr("app.services.vault_sync.get_settings", _settings)
    get_settings.cache_clear()
    vault_db.init_vault_db()
    return settings


def test_sync_discovers_new_file(vault_settings: Settings) -> None:
    vault_root = Path(vault_settings.vault_root)
    folder = vault_root / "news"
    folder.mkdir()
    (folder / "article.md").write_text("# hello", encoding="utf-8")

    with patch("app.services.vault_sync._purge_neo4j"):
        report = sync_vault()

    assert report.drift_added == 1
    row = vault_db.get_file_by_path("news/article.md")
    assert row is not None
    assert row["index_status"] == "not_indexed"


def test_sync_marks_modified_and_purges(vault_settings: Settings) -> None:
    folder = vault_store.create_folder("News")
    created = vault_store.create_text_file(
        folder_id=folder.id, filename="a.md", content="v1"
    )
    vault_db.update_file_fields(
        created.file.id, index_status="indexed", chunk_count=2, content_hash="old"
    )

    path = Path(vault_settings.vault_root) / "news" / "a.md"
    path.write_text("v2 changed", encoding="utf-8")

    mock_purge = MagicMock()
    with patch("app.services.vault_sync._purge_neo4j", mock_purge):
        report = sync_vault()

    assert report.drift_modified == 1
    row = vault_db.get_file_by_id(created.file.id)
    assert row is not None
    assert row["index_status"] == "modified"
    mock_purge.assert_called()


def test_sync_marks_deleted(vault_settings: Settings) -> None:
    folder = vault_store.create_folder("News")
    created = vault_store.create_text_file(
        folder_id=folder.id, filename="gone.md", content="x"
    )
    path = Path(vault_settings.vault_root) / "news" / "gone.md"
    path.unlink()

    with patch("app.services.vault_sync._purge_neo4j") as mock_purge:
        report = sync_vault()

    assert report.drift_removed == 1
    row = vault_db.get_file_by_id(created.file.id)
    assert row is not None
    assert row["index_status"] == "deleted"
    mock_purge.assert_called_with("news/gone.md")
