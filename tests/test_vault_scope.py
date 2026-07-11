"""Tests for vault-scoped search allowlist resolver."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.core.config import Settings, get_settings
from app.services import vault_db
from app.services.vault_scope import (
    AllowlistTooLargeError,
    MAX_ALLOWLIST_PATHS,
    resolve_search_allowlist,
)


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


def _seed_vault() -> None:
    vault_db.init_vault_db()
    vault_db.insert_folder(
        folder_id="f-news",
        name="News",
        slug="news",
        relative_path="news/",
    )
    vault_db.insert_folder(
        folder_id="f-rnd",
        name="RND",
        slug="rnd",
        relative_path="rnd/",
    )
    vault_db.insert_file(
        {
            "id": "file-news-1",
            "folder_id": "f-news",
            "filename": "a.md",
            "relative_path": "news/a.md",
            "source": "created",
            "created_at": "2026-06-01T10:00:00Z",
            "updated_at": "2026-06-01T10:00:00Z",
            "size_bytes": 10,
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
            "id": "file-news-2",
            "folder_id": "f-news",
            "filename": "b.md",
            "relative_path": "news/b.md",
            "source": "created",
            "created_at": "2026-07-01T10:00:00Z",
            "updated_at": "2026-07-01T10:00:00Z",
            "size_bytes": 10,
            "mtime": 1.0,
            "content_hash": None,
            "mime_ext": ".md",
            "mutable": 1,
            "index_status": "not_indexed",
            "chunk_count": 0,
        }
    )
    vault_db.insert_file(
        {
            "id": "file-rnd-1",
            "folder_id": "f-rnd",
            "filename": "c.md",
            "relative_path": "rnd/c.md",
            "source": "created",
            "created_at": "2026-07-15T10:00:00Z",
            "updated_at": "2026-07-15T10:00:00Z",
            "size_bytes": 10,
            "mtime": 1.0,
            "content_hash": None,
            "mime_ext": ".md",
            "mutable": 1,
            "index_status": "indexed",
            "chunk_count": 1,
        }
    )


def test_resolve_all_indexed(vault_env: Path) -> None:
    _seed_vault()
    paths = resolve_search_allowlist(None, None, None, indexed_only=True)
    assert set(paths) == {"news/a.md", "rnd/c.md"}


def test_resolve_folder_filter(vault_env: Path) -> None:
    _seed_vault()
    paths = resolve_search_allowlist(["f-news"], None, None, indexed_only=True)
    assert paths == ["news/a.md"]


def test_resolve_empty_folder_ids(vault_env: Path) -> None:
    _seed_vault()
    assert resolve_search_allowlist([], None, None, True) == []


def test_resolve_indexed_only_false(vault_env: Path) -> None:
    _seed_vault()
    paths = resolve_search_allowlist(["f-news"], None, None, indexed_only=False)
    assert set(paths) == {"news/a.md", "news/b.md"}


def test_resolve_date_range(vault_env: Path) -> None:
    _seed_vault()
    paths = resolve_search_allowlist(
        None,
        date(2026, 7, 1),
        date(2026, 7, 31),
        indexed_only=True,
    )
    assert paths == ["rnd/c.md"]


def test_resolve_allowlist_too_large(vault_env: Path) -> None:
    vault_db.init_vault_db()
    vault_db.insert_folder(
        folder_id="f-bulk",
        name="Bulk",
        slug="bulk",
        relative_path="bulk/",
    )
    for i in range(MAX_ALLOWLIST_PATHS + 1):
        vault_db.insert_file(
            {
                "id": f"file-{i}",
                "folder_id": "f-bulk",
                "filename": f"f{i}.md",
                "relative_path": f"bulk/f{i}.md",
                "source": "created",
                "created_at": vault_db.utc_now(),
                "updated_at": vault_db.utc_now(),
                "size_bytes": 1,
                "mtime": 1.0,
                "content_hash": None,
                "mime_ext": ".md",
                "mutable": 1,
                "index_status": "indexed",
                "chunk_count": 0,
            }
        )
    with pytest.raises(AllowlistTooLargeError):
        resolve_search_allowlist(["f-bulk"], None, None, indexed_only=True)
