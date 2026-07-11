"""Integration tests for vault-scoped search allowlist + Neo4j filter wiring."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.config import Settings, get_settings
from app.services import vault_db
from app.services.vault_scope import resolve_search_allowlist


@pytest.fixture()
def vault_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
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
    get_settings.cache_clear()
    return tmp_path


def _seed_two_folders() -> tuple[str, str]:
    vault_db.init_vault_db()
    vault_db.insert_folder(
        folder_id="f-a", name="FolderA", slug="foldera", relative_path="foldera/"
    )
    vault_db.insert_folder(
        folder_id="f-b", name="FolderB", slug="folderb", relative_path="folderb/"
    )
    vault_db.insert_file(
        {
            "id": "fa1",
            "folder_id": "f-a",
            "filename": "a.md",
            "relative_path": "foldera/a.md",
            "source": "created",
            "created_at": "2026-06-01T10:00:00Z",
            "updated_at": "2026-06-01T10:00:00Z",
            "size_bytes": 1,
            "mtime": 1.0,
            "content_hash": None,
            "mime_ext": ".md",
            "mutable": 1,
            "index_status": "indexed",
            "chunk_count": 1,
        }
    )
    vault_db.insert_file(
        {
            "id": "fb1",
            "folder_id": "f-b",
            "filename": "b.md",
            "relative_path": "folderb/b.md",
            "source": "created",
            "created_at": "2026-07-01T10:00:00Z",
            "updated_at": "2026-07-01T10:00:00Z",
            "size_bytes": 1,
            "mtime": 1.0,
            "content_hash": None,
            "mime_ext": ".md",
            "mutable": 1,
            "index_status": "indexed",
            "chunk_count": 1,
        }
    )
    return "f-a", "f-b"


def test_folder_scope_excludes_other_folder(vault_env: Path) -> None:
    f_a, _ = _seed_two_folders()
    paths = resolve_search_allowlist([f_a], None, None, indexed_only=True)
    assert paths == ["foldera/a.md"]


def test_neo4j_recall_uses_scoped_paths_only(vault_env: Path) -> None:
    f_a, _ = _seed_two_folders()
    paths = resolve_search_allowlist([f_a], None, None, True)

    from app.services.neo4j_client import Neo4jClient

    client = Neo4jClient.__new__(Neo4jClient)
    client._log_query = lambda *a, **k: None

    with patch.object(client, "_run_read", return_value=[]) as mock_read:
        client.bm25_search_chunks("test", 10, allowed_paths=paths)

    _cypher, params = mock_read.call_args[0]
    assert params["allowed_paths"] == ["foldera/a.md"]
    assert "folderb/b.md" not in params["allowed_paths"]


def test_date_scope_narrows_allowlist(vault_env: Path) -> None:
    _seed_two_folders()
    paths = resolve_search_allowlist(
        None,
        date(2026, 6, 1),
        date(2026, 6, 30),
        indexed_only=True,
    )
    assert paths == ["foldera/a.md"]
