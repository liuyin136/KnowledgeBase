"""Drift reconciliation between disk and SQLite for the RAG Content Vault."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.vault_schemas import SyncReport
from app.services import vault_db
from app.services.vault_store import (
    ALLOWED_EXTENSIONS,
    compute_file_hash,
    resolve_vault_path,
)

logger = get_logger("rag.vault.sync")


def _purge_neo4j_ingestion(source_file: str) -> dict[str, int]:
    from app.services.neo4j_client import get_neo4j_client

    return get_neo4j_client().delete_ingestion_tree_for_source(source_file)


def _purge_neo4j(source_file: str) -> None:
    try:
        _purge_neo4j_ingestion(source_file)
    except Exception as exc:
        logger.warning("neo4j_purge_failed", source_file=source_file, error=str(exc))


def _ensure_folder_for_slug(slug: str) -> dict[str, Any]:
    existing = vault_db.get_folder_by_slug(slug)
    if existing:
        return existing
    folder_path = resolve_vault_path(slug)
    folder_path.mkdir(parents=True, exist_ok=True)
    return vault_db.insert_folder(
        folder_id=str(uuid.uuid4()),
        name=slug,
        slug=slug,
        relative_path=f"{slug}/",
    )


def sync_vault(*, force_hash: bool = False) -> SyncReport:
    """Full scan of vault root; reconcile SQLite and purge Neo4j on drift."""
    vault_db.init_vault_db()
    root = Path(get_settings().vault_root)
    root.mkdir(parents=True, exist_ok=True)

    disk_files: dict[str, Path] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue
        if path.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        rel = path.relative_to(root).as_posix()
        if ".." in rel.split("/"):
            continue
        disk_files[rel] = path

    drift_added = 0
    drift_modified = 0
    drift_removed = 0

    for rel, path in disk_files.items():
        parts = rel.split("/", 1)
        if len(parts) != 2:
            # Skip files not under a flat folder
            continue
        slug, filename = parts
        folder = _ensure_folder_for_slug(slug)
        stat = path.stat()
        row = vault_db.get_file_by_path(rel)

        if row is None:
            content_hash = compute_file_hash(path) if force_hash else None
            now = vault_db.utc_now()
            vault_db.insert_file(
                {
                    "id": str(uuid.uuid4()),
                    "folder_id": folder["id"],
                    "filename": filename,
                    "relative_path": rel,
                    "source": "upload",
                    "created_at": now,
                    "updated_at": now,
                    "size_bytes": stat.st_size,
                    "mtime": stat.st_mtime,
                    "content_hash": content_hash,
                    "mime_ext": path.suffix.lower(),
                    "mutable": 1,
                    "index_status": "not_indexed",
                    "chunk_count": 0,
                    "last_ingest_job_id": None,
                    "last_ingest_at": None,
                    "ingest_lock_job_id": None,
                    "error_message": None,
                }
            )
            drift_added += 1
            continue

        size_changed = int(row["size_bytes"]) != stat.st_size
        mtime_changed = abs(float(row["mtime"]) - stat.st_mtime) > 1e-6
        if not size_changed and not mtime_changed and not force_hash:
            continue

        content_hash = compute_file_hash(path)
        fields: dict[str, Any] = {
            "size_bytes": stat.st_size,
            "mtime": stat.st_mtime,
            "content_hash": content_hash,
            "updated_at": vault_db.utc_now(),
        }
        if row["index_status"] in {"indexed", "pending"} or (
            row["content_hash"] and row["content_hash"] != content_hash and row["index_status"] == "indexed"
        ):
            if row["index_status"] == "indexed" and (
                size_changed or mtime_changed or row.get("content_hash") != content_hash
            ):
                fields["index_status"] = "modified"
                fields["chunk_count"] = 0
                _purge_neo4j(rel)
                drift_modified += 1
        vault_db.update_file_fields(row["id"], **fields)

    for row in vault_db.list_active_files():
        rel = row["relative_path"]
        if rel in disk_files:
            continue
        _purge_neo4j(rel)
        vault_db.mark_file_deleted(row["id"])
        drift_removed += 1

    state = vault_db.update_sync_state(
        files_scanned=len(disk_files),
        drift_modified=drift_modified,
        drift_added=drift_added,
        drift_removed=drift_removed,
    )
    report = SyncReport(
        files_scanned=len(disk_files),
        drift_added=drift_added,
        drift_modified=drift_modified,
        drift_removed=drift_removed,
        last_sync_at=state.get("last_sync_at"),
    )
    logger.info(
        "vault_sync_complete",
        files_scanned=report.files_scanned,
        drift_added=report.drift_added,
        drift_modified=report.drift_modified,
        drift_removed=report.drift_removed,
    )
    return report


def sync_vault_for_path(relative_path: str) -> None:
    """Lightweight check before ingest for a single vault path."""
    row = vault_db.get_file_by_path(relative_path)
    root = Path(get_settings().vault_root)
    path = root / relative_path
    if not path.is_file():
        if row and row["index_status"] != "deleted":
            _purge_neo4j(relative_path)
            vault_db.mark_file_deleted(row["id"])
        return
    if row is None:
        sync_vault()
        return
    stat = path.stat()
    if int(row["size_bytes"]) == stat.st_size and abs(float(row["mtime"]) - stat.st_mtime) <= 1e-6:
        return
    content_hash = compute_file_hash(path)
    fields: dict[str, Any] = {
        "size_bytes": stat.st_size,
        "mtime": stat.st_mtime,
        "content_hash": content_hash,
        "updated_at": vault_db.utc_now(),
    }
    if row["index_status"] == "indexed":
        fields["index_status"] = "modified"
        fields["chunk_count"] = 0
        _purge_neo4j(relative_path)
    vault_db.update_file_fields(row["id"], **fields)
