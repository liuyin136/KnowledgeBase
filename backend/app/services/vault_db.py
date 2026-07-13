"""SQLite metadata store for the RAG Content Vault."""
from __future__ import annotations

import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("rag.vault_db")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS vault_folders (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    relative_path TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS vault_files (
    id TEXT PRIMARY KEY,
    folder_id TEXT NOT NULL REFERENCES vault_folders(id),
    filename TEXT NOT NULL,
    relative_path TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    mtime REAL NOT NULL DEFAULT 0,
    content_hash TEXT,
    mime_ext TEXT NOT NULL,
    mutable INTEGER NOT NULL DEFAULT 1,
    index_status TEXT NOT NULL DEFAULT 'not_indexed',
    chunk_count INTEGER NOT NULL DEFAULT 0,
    last_ingest_job_id TEXT,
    last_ingest_at TEXT,
    ingest_lock_job_id TEXT,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_vault_files_folder_id ON vault_files(folder_id);
CREATE INDEX IF NOT EXISTS idx_vault_files_index_status ON vault_files(index_status);
CREATE INDEX IF NOT EXISTS idx_vault_files_created_at ON vault_files(created_at);

CREATE TABLE IF NOT EXISTS vault_sync_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_sync_at TEXT,
    files_scanned INTEGER NOT NULL DEFAULT 0,
    drift_modified INTEGER NOT NULL DEFAULT 0,
    drift_added INTEGER NOT NULL DEFAULT 0,
    drift_removed INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS vault_batches (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    total_files INTEGER NOT NULL DEFAULT 0,
    completed_files INTEGER NOT NULL DEFAULT 0,
    failed_files INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS vault_batch_files (
    batch_id TEXT NOT NULL REFERENCES vault_batches(id),
    file_id TEXT NOT NULL,
    job_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    PRIMARY KEY (batch_id, file_id)
);

CREATE TABLE IF NOT EXISTS vault_doc_meta (
    file_id TEXT PRIMARY KEY REFERENCES vault_files(id) ON DELETE CASCADE,
    raw_yaml TEXT,
    fields_json TEXT NOT NULL DEFAULT '{}',
    parsed_at TEXT NOT NULL
);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_vault_dirs() -> None:
    settings = get_settings()
    Path(settings.vault_root).mkdir(parents=True, exist_ok=True)
    Path(settings.vault_db_path).parent.mkdir(parents=True, exist_ok=True)


def _legacy_vault_db_path() -> Path:
    settings = get_settings()
    return Path(settings.data_root) / "rag" / "vault.db"


def _migrate_legacy_vault_db_if_needed() -> None:
    """Copy bind-mount vault.db to named volume path on first Docker boot."""
    settings = get_settings()
    target = Path(settings.vault_db_path)
    if target.exists():
        return
    legacy = _legacy_vault_db_path()
    if not legacy.is_file():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(legacy, target)
    logger.info(
        "vault_db_migrated_from_legacy",
        legacy=str(legacy),
        target=str(target),
    )


def _set_journal_mode(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        conn.execute("PRAGMA journal_mode=DELETE")


def _configure_pragmas(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    _set_journal_mode(conn)
    conn.execute("PRAGMA foreign_keys=ON")


def init_vault_db() -> None:
    ensure_vault_dirs()
    _migrate_legacy_vault_db_if_needed()
    with get_connection() as conn:
        conn.executescript(SCHEMA_SQL)
        conn.execute(
            "INSERT OR IGNORE INTO vault_sync_state (id, last_sync_at, files_scanned, "
            "drift_modified, drift_added, drift_removed) VALUES (1, NULL, 0, 0, 0, 0)"
        )
        conn.commit()


@contextmanager
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    settings = get_settings()
    Path(settings.vault_db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.vault_db_path, timeout=30)
    _configure_pragmas(conn)
    try:
        yield conn
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def get_folder_by_id(folder_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM vault_folders WHERE id = ?", (folder_id,)
        ).fetchone()
        return row_to_dict(row)


def get_folder_by_slug(slug: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM vault_folders WHERE slug = ?", (slug,)
        ).fetchone()
        return row_to_dict(row)


def list_folders() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM vault_folders ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [dict(r) for r in rows]


def insert_folder(
    *,
    folder_id: str,
    name: str,
    slug: str,
    relative_path: str,
) -> dict[str, Any]:
    now = _utc_now()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO vault_folders (id, name, slug, created_at, relative_path) "
            "VALUES (?, ?, ?, ?, ?)",
            (folder_id, name, slug, now, relative_path),
        )
        conn.commit()
    return get_folder_by_id(folder_id)  # type: ignore[return-value]


def update_folder(
    folder_id: str,
    *,
    name: str | None = None,
    slug: str | None = None,
    relative_path: str | None = None,
) -> dict[str, Any] | None:
    folder = get_folder_by_id(folder_id)
    if not folder:
        return None
    new_name = name if name is not None else folder["name"]
    new_slug = slug if slug is not None else folder["slug"]
    new_rel = relative_path if relative_path is not None else folder["relative_path"]
    with get_connection() as conn:
        conn.execute(
            "UPDATE vault_folders SET name = ?, slug = ?, relative_path = ? WHERE id = ?",
            (new_name, new_slug, new_rel, folder_id),
        )
        conn.commit()
    return get_folder_by_id(folder_id)


def delete_folder_row(folder_id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM vault_folders WHERE id = ?", (folder_id,))
        conn.commit()


def count_files_in_folder(folder_id: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM vault_files WHERE folder_id = ? AND index_status != 'deleted'",
            (folder_id,),
        ).fetchone()
        return int(row["c"]) if row else 0


def get_file_by_id(file_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM vault_files WHERE id = ?", (file_id,)
        ).fetchone()
        return row_to_dict(row)


def get_file_by_path(relative_path: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM vault_files WHERE relative_path = ?", (relative_path,)
        ).fetchone()
        return row_to_dict(row)


def list_active_files() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM vault_files WHERE index_status != 'deleted'"
        ).fetchall()
        return [dict(r) for r in rows]


def list_files_in_folder(folder_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM vault_files WHERE folder_id = ? AND index_status != 'deleted'",
            (folder_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def folder_has_locked_files(folder_id: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM vault_files WHERE folder_id = ? "
            "AND index_status != 'deleted' AND ingest_lock_job_id IS NOT NULL LIMIT 1",
            (folder_id,),
        ).fetchone()
        return row is not None


def list_files_paginated(
    *,
    folder_id: str | None = None,
    keyword: str | None = None,
    index_status: str | None = None,
    search_content: bool = False,
    page: int = 1,
    page_size: int = 10,
    content_matcher: Any = None,
    content_scan_limit: int = 200,
) -> tuple[list[dict[str, Any]], int]:
    clauses = ["index_status != 'deleted'"]
    params: list[Any] = []
    if folder_id:
        clauses.append("folder_id = ?")
        params.append(folder_id)
    if index_status:
        clauses.append("index_status = ?")
        params.append(index_status)

    if keyword and content_matcher is not None:
        scan_clauses = list(clauses)
        scan_params = list(params)
        where_scan = " AND ".join(scan_clauses)
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM vault_files WHERE {where_scan} ORDER BY created_at DESC LIMIT ?",
                [*scan_params, content_scan_limit],
            ).fetchall()
        kw = keyword.lower()
        matched = [
            dict(r)
            for r in rows
            if kw in r["filename"].lower()
            or kw in r["relative_path"].lower()
            or content_matcher(r["relative_path"], keyword)
        ]
        total = len(matched)
        offset = max(page - 1, 0) * page_size
        return matched[offset : offset + page_size], total

    if keyword:
        clauses.append("(filename LIKE ? OR relative_path LIKE ?)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    where = " AND ".join(clauses)
    with get_connection() as conn:
        total_row = conn.execute(
            f"SELECT COUNT(*) AS c FROM vault_files WHERE {where}", params
        ).fetchone()
        total = int(total_row["c"]) if total_row else 0
        offset = max(page - 1, 0) * page_size
        rows = conn.execute(
            f"SELECT * FROM vault_files WHERE {where} "
            f"ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [*params, page_size, offset],
        ).fetchall()
        return [dict(r) for r in rows], total


def insert_file(row: dict[str, Any]) -> dict[str, Any]:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO vault_files (
                id, folder_id, filename, relative_path, source, created_at, updated_at,
                size_bytes, mtime, content_hash, mime_ext, mutable, index_status,
                chunk_count, last_ingest_job_id, last_ingest_at, ingest_lock_job_id,
                error_message
            ) VALUES (
                :id, :folder_id, :filename, :relative_path, :source, :created_at, :updated_at,
                :size_bytes, :mtime, :content_hash, :mime_ext, :mutable, :index_status,
                :chunk_count, :last_ingest_job_id, :last_ingest_at, :ingest_lock_job_id,
                :error_message
            )
            """,
            {
                "id": row["id"],
                "folder_id": row["folder_id"],
                "filename": row["filename"],
                "relative_path": row["relative_path"],
                "source": row["source"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "size_bytes": row.get("size_bytes", 0),
                "mtime": row.get("mtime", 0.0),
                "content_hash": row.get("content_hash"),
                "mime_ext": row["mime_ext"],
                "mutable": row.get("mutable", 1),
                "index_status": row.get("index_status", "not_indexed"),
                "chunk_count": row.get("chunk_count", 0),
                "last_ingest_job_id": row.get("last_ingest_job_id"),
                "last_ingest_at": row.get("last_ingest_at"),
                "ingest_lock_job_id": row.get("ingest_lock_job_id"),
                "error_message": row.get("error_message"),
            },
        )
        conn.commit()
    return get_file_by_id(row["id"])  # type: ignore[return-value]


def update_file_fields(file_id: str, **fields: Any) -> dict[str, Any] | None:
    if not fields:
        return get_file_by_id(file_id)
    cols = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values())
    values.append(file_id)
    with get_connection() as conn:
        conn.execute(f"UPDATE vault_files SET {cols} WHERE id = ?", values)
        conn.commit()
    return get_file_by_id(file_id)


def update_file_status(
    file_id: str,
    *,
    index_status: str,
    chunk_count: int | None = None,
    content_hash: str | None = None,
    last_ingest_job_id: str | None = None,
    last_ingest_at: str | None = None,
    ingest_lock_job_id: str | None = ...,  # type: ignore[assignment]
    error_message: str | None = None,
) -> dict[str, Any] | None:
    fields: dict[str, Any] = {"index_status": index_status, "updated_at": _utc_now()}
    if chunk_count is not None:
        fields["chunk_count"] = chunk_count
    if content_hash is not None:
        fields["content_hash"] = content_hash
    if last_ingest_job_id is not None:
        fields["last_ingest_job_id"] = last_ingest_job_id
    if last_ingest_at is not None:
        fields["last_ingest_at"] = last_ingest_at
    if ingest_lock_job_id is not ...:
        fields["ingest_lock_job_id"] = ingest_lock_job_id
    if error_message is not None:
        fields["error_message"] = error_message[:500]
    return update_file_fields(file_id, **fields)


def set_file_pending(relative_path: str, job_id: str) -> dict[str, Any] | None:
    row = get_file_by_path(relative_path)
    if not row:
        return None
    return update_file_status(
        row["id"],
        index_status="pending",
        last_ingest_job_id=job_id,
        ingest_lock_job_id=job_id,
        error_message="",
    )


def clear_file_lock(
    relative_path: str,
    *,
    index_status: str,
    chunk_count: int | None = None,
    content_hash: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any] | None:
    row = get_file_by_path(relative_path)
    if not row:
        return None
    return update_file_status(
        row["id"],
        index_status=index_status,
        chunk_count=chunk_count,
        content_hash=content_hash,
        last_ingest_at=_utc_now() if index_status == "indexed" else None,
        ingest_lock_job_id=None,
        error_message=error_message or "",
    )


def clear_file_lock_by_id(
    file_id: str,
    *,
    index_status: str,
    chunk_count: int | None = None,
    content_hash: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any] | None:
    row = get_file_by_id(file_id)
    if not row or row["index_status"] == "deleted":
        return None
    return update_file_status(
        file_id,
        index_status=index_status,
        chunk_count=chunk_count,
        content_hash=content_hash,
        last_ingest_at=_utc_now() if index_status == "indexed" else None,
        ingest_lock_job_id=None,
        error_message=error_message or "",
    )


def update_file_paths_prefix(old_prefix: str, new_prefix: str) -> int:
    """Update relative_path for all files under a renamed folder."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, relative_path FROM vault_files WHERE relative_path LIKE ?",
            (f"{old_prefix}%",),
        ).fetchall()
        count = 0
        for row in rows:
            new_path = new_prefix + row["relative_path"][len(old_prefix) :]
            conn.execute(
                "UPDATE vault_files SET relative_path = ?, updated_at = ? WHERE id = ?",
                (new_path, _utc_now(), row["id"]),
            )
            count += 1
        conn.commit()
        return count


def delete_file_row(file_id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM vault_files WHERE id = ?", (file_id,))
        conn.commit()


def mark_file_deleted(file_id: str) -> None:
    update_file_fields(
        file_id,
        index_status="deleted",
        updated_at=_utc_now(),
        ingest_lock_job_id=None,
    )


def get_sync_state() -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM vault_sync_state WHERE id = 1").fetchone()
        return dict(row) if row else {
            "id": 1,
            "last_sync_at": None,
            "files_scanned": 0,
            "drift_modified": 0,
            "drift_added": 0,
            "drift_removed": 0,
        }


def update_sync_state(
    *,
    files_scanned: int,
    drift_modified: int,
    drift_added: int,
    drift_removed: int,
) -> dict[str, Any]:
    now = _utc_now()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE vault_sync_state SET
                last_sync_at = ?,
                files_scanned = ?,
                drift_modified = ?,
                drift_added = ?,
                drift_removed = ?
            WHERE id = 1
            """,
            (now, files_scanned, drift_modified, drift_added, drift_removed),
        )
        conn.commit()
    return get_sync_state()


def wipe_vault_metadata() -> None:
    """Clear vault SQLite tables. Disk files under vault_root are untouched."""
    with get_connection() as conn:
        conn.execute("DELETE FROM vault_batch_files")
        conn.execute("DELETE FROM vault_batches")
        conn.execute("DELETE FROM vault_doc_meta")
        conn.execute("DELETE FROM vault_files")
        conn.execute("DELETE FROM vault_folders")
        conn.execute(
            "UPDATE vault_sync_state SET last_sync_at = NULL, files_scanned = 0, "
            "drift_modified = 0, drift_added = 0, drift_removed = 0 WHERE id = 1"
        )
        conn.commit()


def upsert_doc_meta(
    file_id: str,
    *,
    raw_yaml: str | None,
    fields: dict[str, Any],
) -> dict[str, Any]:
    import json

    now = _utc_now()
    fields_json = json.dumps(fields, ensure_ascii=False)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO vault_doc_meta (file_id, raw_yaml, fields_json, parsed_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(file_id) DO UPDATE SET
                raw_yaml = excluded.raw_yaml,
                fields_json = excluded.fields_json,
                parsed_at = excluded.parsed_at
            """,
            (file_id, raw_yaml, fields_json, now),
        )
        conn.commit()
    return get_doc_meta(file_id)  # type: ignore[return-value]


def get_doc_meta(file_id: str) -> dict[str, Any] | None:
    import json

    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM vault_doc_meta WHERE file_id = ?", (file_id,)
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        try:
            data["fields"] = json.loads(data.get("fields_json") or "{}")
        except json.JSONDecodeError:
            data["fields"] = {}
        return data


def delete_doc_meta(file_id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM vault_doc_meta WHERE file_id = ?", (file_id,))
        conn.commit()


def insert_batch(*, batch_id: str, total_files: int) -> dict[str, Any]:
    now = _utc_now()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO vault_batches (id, created_at, total_files, completed_files, failed_files) "
            "VALUES (?, ?, ?, 0, 0)",
            (batch_id, now, total_files),
        )
        conn.commit()
    return get_batch(batch_id)  # type: ignore[return-value]


def get_batch(batch_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM vault_batches WHERE id = ?", (batch_id,)
        ).fetchone()
        return row_to_dict(row)


def add_batch_file(batch_id: str, file_id: str, job_id: str | None = None) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO vault_batch_files (batch_id, file_id, job_id, status) VALUES (?, ?, ?, ?)",
            (batch_id, file_id, job_id, "pending"),
        )
        conn.commit()


def list_batch_files(batch_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM vault_batch_files WHERE batch_id = ?", (batch_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def update_batch_file_status(
    batch_id: str, file_id: str, *, status: str, job_id: str | None = None
) -> None:
    with get_connection() as conn:
        if job_id is not None:
            conn.execute(
                "UPDATE vault_batch_files SET status = ?, job_id = ? WHERE batch_id = ? AND file_id = ?",
                (status, job_id, batch_id, file_id),
            )
        else:
            conn.execute(
                "UPDATE vault_batch_files SET status = ? WHERE batch_id = ? AND file_id = ?",
                (status, batch_id, file_id),
            )
        conn.commit()


def refresh_batch_counts(batch_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        completed = conn.execute(
            "SELECT COUNT(*) AS c FROM vault_batch_files WHERE batch_id = ? AND status = 'completed'",
            (batch_id,),
        ).fetchone()
        failed = conn.execute(
            "SELECT COUNT(*) AS c FROM vault_batch_files WHERE batch_id = ? AND status = 'failed'",
            (batch_id,),
        ).fetchone()
        conn.execute(
            "UPDATE vault_batches SET completed_files = ?, failed_files = ? WHERE id = ?",
            (int(completed["c"]), int(failed["c"]), batch_id),
        )
        conn.commit()
    return get_batch(batch_id)


def utc_now() -> str:
    return _utc_now()
