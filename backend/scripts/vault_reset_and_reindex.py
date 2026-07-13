"""Phase 1.62 vault reconstruct / migration CLI.

Default: **destructive** reconstruct — delete vault disk files, purge Neo4j
ingestion (all tiers), clear Redis caches, wipe SQLite (incl. vault_doc_meta).

Usage (from project root):

  docker compose run --rm api-worker python scripts/vault_reset_and_reindex.py --dry-run
  docker compose run --rm api-worker python scripts/vault_reset_and_reindex.py

  # Keep vault files on disk; purge indexes and reindex:
  docker compose run --rm api-worker python scripts/vault_reset_and_reindex.py --keep-disk

  # Legacy v1.6-style migration (no disk delete):
  docker compose run --rm api-worker python scripts/vault_reset_and_reindex.py --legacy-migrate
"""
from __future__ import annotations

import argparse
import sys

from app.core.config import get_settings
from app.services import vault_db
from app.services.vault_migration import (
    _disk_vault_paths,
    known_vault_sources,
    run_full_v162_reconstruct,
    run_full_vault_migration,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 1.62 vault reconstruct: purge Neo4j/Redis/SQLite; optionally delete disk files."
    )
    parser.add_argument(
        "--keep-disk",
        action="store_true",
        help="Do not delete vault files on disk; resync + reindex after purge",
    )
    parser.add_argument(
        "--skip-reindex",
        action="store_true",
        help="With --keep-disk: purge + sync only; do not enqueue ingest",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned actions without writes",
    )
    parser.add_argument(
        "--legacy-migrate",
        action="store_true",
        help="Use pre-1.62 migration (no disk delete; enqueue reindex)",
    )
    parser.add_argument(
        "--neo4j",
        choices=("vault", "all"),
        default="all",
        help="Only used with --legacy-migrate",
    )
    args = parser.parse_args()

    vault_db.init_vault_db()
    settings = get_settings()
    disk_count = len(_disk_vault_paths())

    print(f"Vault root: {settings.vault_root}")
    print(f"Vault DB:   {settings.vault_db_path}")
    print(f"Disk files: {disk_count}")

    if args.legacy_migrate:
        sources = known_vault_sources()
        print(f"Mode: legacy migrate (neo4j={args.neo4j})")
        if args.dry_run:
            print("[dry-run] Would purge Neo4j:", "all" if args.neo4j == "all" else sources)
            print("[dry-run] Would clear Redis + wipe SQLite + sync")
            if not args.skip_reindex:
                print(f"[dry-run] Would enqueue ingest for {disk_count} file(s)")
            return
        report = run_full_vault_migration(
            dry_run=False,
            purge_mode=args.neo4j,
            skip_reindex=args.skip_reindex,
        )
        print(f"Neo4j purged: {report.neo4j_stats}")
        print(f"Redis keys deleted: {report.redis_keys_deleted}")
        print(f"Enqueued {len(report.job_ids)} ingest job(s)")
        return

    delete_disk = not args.keep_disk
    print(f"Mode: v1.62 reconstruct (delete_disk={delete_disk})")

    if args.dry_run:
        if delete_disk:
            print(f"[dry-run] Would DELETE {disk_count} vault file(s) on disk")
        print("[dry-run] Would purge all Neo4j ingestion nodes (v1.62 labels)")
        print("[dry-run] Would clear Redis ingest/search/retrieval caches")
        print("[dry-run] Would wipe vault SQLite metadata (incl. vault_doc_meta)")
        if not delete_disk:
            print("[dry-run] Would run sync_vault(force_hash=True)")
            if not args.skip_reindex:
                print(f"[dry-run] Would enqueue ingest for {disk_count} file(s)")
        else:
            print("[dry-run] Empty vault — re-upload files via Library after reconstruct")
        return

    report = run_full_v162_reconstruct(
        dry_run=False,
        delete_disk=delete_disk,
        skip_reindex=args.skip_reindex,
    )
    print(f"Disk files deleted: {report.disk_files_deleted}")
    print(f"Neo4j purged: {report.neo4j_stats}")
    print(f"Redis keys deleted: {report.redis_keys_deleted}")
    print("Vault SQLite metadata wiped")
    sr = report.sync_report
    if sr:
        print(
            f"Sync: scanned={sr.get('files_scanned', 0)} "
            f"added={sr.get('drift_added', 0)} modified={sr.get('drift_modified', 0)} "
            f"removed={sr.get('drift_removed', 0)}"
        )
    if delete_disk:
        print("Vault empty. Re-upload documents via /rag/library, then wait for 10-phase ingest.")
        return
    if args.skip_reindex:
        print("Skipping reindex (--skip-reindex)")
        return
    if not report.job_ids:
        print("No vault files to ingest")
        return
    print(f"Enqueued {len(report.job_ids)} ingest job(s):")
    for entry in report.job_ids:
        print(f"  {entry.relative_path} -> {entry.ingest_job_id}")
    print("Ensure api-worker is running: docker compose ps api-worker")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"vault_reset_and_reindex failed: {exc}", file=sys.stderr)
        sys.exit(1)
