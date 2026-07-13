"""Shared full v1.6 vault migration: Neo4j purge, Redis cache clear, sync, reindex."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.core.config import get_settings
from app.services import vault_db
from app.services.job_queue import enqueue_vault_ingest, get_redis_connection
from app.services.neo4j_client import get_neo4j_client
from app.services.vault_store import ALLOWED_EXTENSIONS
from app.services.vault_sync import sync_vault

PurgeMode = Literal["vault", "all"]

_REDIS_PATTERNS = (
    "ingest:*",
    "search:*",
    "retrieval:tree:*",
    "search:pending_rerank:*",
)


@dataclass
class MigrationJobEntry:
    file_id: str
    relative_path: str
    ingest_job_id: str


@dataclass
class MigrationReport:
    purge_mode: PurgeMode
    dry_run: bool
    neo4j_stats: dict[str, int] = field(default_factory=dict)
    redis_keys_deleted: int = 0
    sync_report: dict[str, Any] = field(default_factory=dict)
    total_files: int = 0
    job_ids: list[MigrationJobEntry] = field(default_factory=list)
    skipped_reindex: bool = False


def _disk_vault_paths() -> list[str]:
    root = Path(get_settings().vault_root)
    if not root.is_dir():
        return []
    paths: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        rel = path.relative_to(root).as_posix()
        if ".." in rel.split("/") or "/" not in rel:
            continue
        paths.append(rel)
    return paths


def known_vault_sources() -> list[str]:
    sqlite_paths = [row["relative_path"] for row in vault_db.list_active_files()]
    return sorted(set(_disk_vault_paths()) | set(sqlite_paths))


def any_ingest_locked() -> bool:
    with vault_db.get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM vault_files WHERE index_status != 'deleted' "
            "AND ingest_lock_job_id IS NOT NULL LIMIT 1"
        ).fetchone()
        return row is not None


def clear_migration_redis_caches() -> int:
    conn = get_redis_connection()
    deleted = 0
    for pattern in _REDIS_PATTERNS:
        for key in conn.scan_iter(match=pattern):
            conn.delete(key)
            deleted += 1
    return deleted


def run_full_vault_migration(
    *,
    dry_run: bool = False,
    purge_mode: PurgeMode = "vault",
    skip_reindex: bool = True,
) -> MigrationReport:
    vault_db.init_vault_db()
    sources = known_vault_sources()
    report = MigrationReport(purge_mode=purge_mode, dry_run=dry_run, skipped_reindex=skip_reindex)

    if dry_run:
        report.neo4j_stats = {"sources": len(sources)}
        report.total_files = len(_disk_vault_paths())
        return report

    neo = get_neo4j_client()
    if purge_mode == "all":
        report.neo4j_stats = neo.delete_all_ingestion()
    else:
        report.neo4j_stats = neo.delete_all_vault_ingestion(sources)

    report.redis_keys_deleted = clear_migration_redis_caches()

    vault_db.wipe_vault_metadata()
    sync_result = sync_vault(force_hash=True)
    report.sync_report = {
        "files_scanned": sync_result.files_scanned,
        "drift_added": sync_result.drift_added,
        "drift_modified": sync_result.drift_modified,
        "drift_removed": sync_result.drift_removed,
        "last_sync_at": sync_result.last_sync_at,
    }

    if skip_reindex:
        report.total_files = len(vault_db.list_active_files())
        return report

    files = vault_db.list_active_files()
    report.total_files = len(files)
    for row in files:
        job_id = enqueue_vault_ingest(row["id"])
        report.job_ids.append(
            MigrationJobEntry(
                file_id=row["id"],
                relative_path=row["relative_path"],
                ingest_job_id=job_id,
            )
        )
    return report


@dataclass
class ReconstructReport:
    dry_run: bool
    delete_disk: bool
    disk_files_deleted: int = 0
    neo4j_stats: dict[str, int] = field(default_factory=dict)
    redis_keys_deleted: int = 0
    sync_report: dict[str, Any] = field(default_factory=dict)
    total_files: int = 0
    job_ids: list[MigrationJobEntry] = field(default_factory=list)
    skipped_reindex: bool = False


def _delete_vault_disk_files() -> int:
    """Delete all allowed vault files under vault_root; keep directory structure."""
    root = Path(get_settings().vault_root)
    if not root.is_dir():
        return 0
    deleted = 0
    for path in sorted(root.rglob("*"), reverse=True):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        path.unlink(missing_ok=True)
        deleted += 1
    return deleted


def run_full_v162_reconstruct(
    *,
    dry_run: bool = False,
    delete_disk: bool = True,
    skip_reindex: bool = True,
) -> ReconstructReport:
    """
    Destructive Phase 1.62 reconstruct.

    Default: delete vault disk files + Neo4j ingestion + Redis caches + SQLite metadata.
    With delete_disk=False (--keep-disk): purge indexes and resync/reindex existing files.
    """
    vault_db.init_vault_db()
    disk_paths = _disk_vault_paths()
    report = ReconstructReport(
        dry_run=dry_run,
        delete_disk=delete_disk,
        skipped_reindex=skip_reindex,
    )

    if dry_run:
        report.disk_files_deleted = len(disk_paths) if delete_disk else 0
        report.total_files = 0 if delete_disk else len(disk_paths)
        report.neo4j_stats = {"would_purge": "all_ingestion"}
        return report

    if delete_disk:
        report.disk_files_deleted = _delete_vault_disk_files()

    neo = get_neo4j_client()
    report.neo4j_stats = neo.delete_all_ingestion()
    report.redis_keys_deleted = clear_migration_redis_caches()
    vault_db.wipe_vault_metadata()
    vault_db.init_vault_db()  # recreate vault_doc_meta schema

    if delete_disk:
        # Empty slate — nothing to sync/enqueue
        report.sync_report = {
            "files_scanned": 0,
            "drift_added": 0,
            "drift_modified": 0,
            "drift_removed": 0,
            "last_sync_at": None,
        }
        report.total_files = 0
        return report

    sync_result = sync_vault(force_hash=True)
    report.sync_report = {
        "files_scanned": sync_result.files_scanned,
        "drift_added": sync_result.drift_added,
        "drift_modified": sync_result.drift_modified,
        "drift_removed": sync_result.drift_removed,
        "last_sync_at": sync_result.last_sync_at,
    }

    if skip_reindex:
        report.total_files = len(vault_db.list_active_files())
        return report

    files = vault_db.list_active_files()
    report.total_files = len(files)
    for row in files:
        job_id = enqueue_vault_ingest(row["id"])
        report.job_ids.append(
            MigrationJobEntry(
                file_id=row["id"],
                relative_path=row["relative_path"],
                ingest_job_id=job_id,
            )
        )
    return report
