"""Tests for vault SQLite schema and helpers."""
from __future__ import annotations

from pathlib import Path

import pytest
import sqlite3

from app.core.config import Settings, get_settings
from app.services import vault_db


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


def test_init_vault_db_idempotent(vault_env: Path) -> None:
    vault_db.init_vault_db()
    vault_db.init_vault_db()

    with vault_db.get_connection() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        cols = {row[1] for row in conn.execute("PRAGMA table_info(vault_files)").fetchall()}

    assert "vault_folders" in tables
    assert "vault_files" in tables
    assert "vault_sync_state" in tables
    assert "vault_batches" in tables
    assert "vault_batch_files" in tables
    assert "mtime" in cols
    assert "ingest_lock_job_id" in cols
    assert "error_message" in cols
    assert "content_hash" in cols


def test_insert_and_paginate_files(vault_env: Path) -> None:
    vault_db.init_vault_db()
    folder = vault_db.insert_folder(
        folder_id="f1",
        name="News",
        slug="news",
        relative_path="news/",
    )
    assert folder["slug"] == "news"

    for i in range(12):
        vault_db.insert_file(
            {
                "id": f"file-{i}",
                "folder_id": "f1",
                "filename": f"article-{i}.md",
                "relative_path": f"news/article-{i}.md",
                "source": "created",
                "created_at": vault_db.utc_now(),
                "updated_at": vault_db.utc_now(),
                "size_bytes": 10,
                "mtime": 1.0,
                "content_hash": None,
                "mime_ext": ".md",
                "mutable": 1,
                "index_status": "not_indexed",
                "chunk_count": 0,
                "last_ingest_job_id": None,
                "last_ingest_at": None,
                "ingest_lock_job_id": None,
                "error_message": None,
            }
        )

    rows, total = vault_db.list_files_paginated(page=1, page_size=10)
    assert total == 12
    assert len(rows) == 10

    rows2, _ = vault_db.list_files_paginated(page=2, page_size=10)
    assert len(rows2) == 2


def test_set_pending_and_clear_lock(vault_env: Path) -> None:
    vault_db.init_vault_db()
    vault_db.insert_folder(
        folder_id="f1", name="News", slug="news", relative_path="news/"
    )
    vault_db.insert_file(
        {
            "id": "file-1",
            "folder_id": "f1",
            "filename": "a.md",
            "relative_path": "news/a.md",
            "source": "created",
            "created_at": vault_db.utc_now(),
            "updated_at": vault_db.utc_now(),
            "size_bytes": 1,
            "mtime": 1.0,
            "content_hash": None,
            "mime_ext": ".md",
            "mutable": 1,
            "index_status": "not_indexed",
            "chunk_count": 0,
            "last_ingest_job_id": None,
            "last_ingest_at": None,
            "ingest_lock_job_id": None,
            "error_message": None,
        }
    )
    pending = vault_db.set_file_pending("news/a.md", "job-1")
    assert pending is not None
    assert pending["index_status"] == "pending"
    assert pending["ingest_lock_job_id"] == "job-1"

    done = vault_db.clear_file_lock(
        "news/a.md", index_status="indexed", chunk_count=3, content_hash="abc"
    )
    assert done is not None
    assert done["index_status"] == "indexed"
    assert done["ingest_lock_job_id"] is None
    assert done["chunk_count"] == 3


def test_journal_mode_fallback_on_wal_error() -> None:
    class ConnStub:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def execute(self, sql: str, *args: object, **kwargs: object) -> "ConnStub":
            self.calls.append(sql)
            if "journal_mode=WAL" in sql:
                raise sqlite3.OperationalError("simulated WAL failure")
            return self

    stub = ConnStub()
    vault_db._set_journal_mode(stub)
    assert any("journal_mode=DELETE" in c for c in stub.calls)
    assert any("journal_mode=WAL" in c for c in stub.calls)
