"""Reset vault SQLite + Neo4j, resync from disk, enqueue ingest for /rag/library files.

Does not delete files on disk under ``/data/rag/vault/``.

Usage (from project root; api-worker must be running to process ingest jobs):

  docker compose run --rm api-worker python scripts/vault_reset_and_reindex.py

  # Also wipe experiment / legacy Knowledge nodes in Neo4j:
  docker compose run --rm api-worker python scripts/vault_reset_and_reindex.py --neo4j all

  # Preview without changes:
  docker compose run --rm api-worker python scripts/vault_reset_and_reindex.py --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.core.config import get_settings
from app.services import vault_db
from app.services.job_queue import enqueue_vault_ingest
from app.services.neo4j_client import get_neo4j_client
from app.services.vault_store import ALLOWED_EXTENSIONS
from app.services.vault_sync import sync_vault


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


def _known_vault_sources() -> list[str]:
    sqlite_paths = [
        row["relative_path"]
        for row in vault_db.list_active_files()
    ]
    return sorted(set(_disk_vault_paths()) | set(sqlite_paths))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Wipe vault SQLite + Neo4j vault knowledge, resync disk, reindex library."
    )
    parser.add_argument(
        "--neo4j",
        choices=("vault", "all"),
        default="vault",
        help="vault: purge only library source_file paths; all: delete every :Knowledge node",
    )
    parser.add_argument(
        "--skip-reindex",
        action="store_true",
        help="Reset metadata only; do not enqueue ingest jobs",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned actions without modifying SQLite or Neo4j",
    )
    args = parser.parse_args()

    vault_db.init_vault_db()
    settings = get_settings()
    sources = _known_vault_sources()

    print(f"Vault root: {settings.vault_root}")
    print(f"Vault DB:   {settings.vault_db_path}")
    print(f"Disk files: {len(_disk_vault_paths())}")
    print(f"Neo4j mode: {args.neo4j}")

    if args.dry_run:
        print("[dry-run] Would purge Neo4j:", "all Knowledge" if args.neo4j == "all" else sources)
        print("[dry-run] Would wipe vault SQLite metadata")
        print("[dry-run] Would run sync_vault(force_hash=True)")
        if not args.skip_reindex:
            print(f"[dry-run] Would enqueue ingest for {len(_disk_vault_paths())} file(s)")
        return

    neo = get_neo4j_client()
    if args.neo4j == "all":
        stats = neo.delete_all_knowledge()
        print(
            f"Neo4j purged all Knowledge: {stats['knowledge_deleted']} parents, "
            f"{stats['chunks_deleted']} chunks"
        )
    else:
        total_chunks = 0
        for rel in sources:
            total_chunks += neo.delete_knowledge_by_source(rel)
        bench = neo.delete_knowledge_by_prefix("_benchmark/")
        print(
            f"Neo4j purged {len(sources)} vault source(s), {total_chunks} chunk(s); "
            f"benchmark parents removed: {bench['knowledge_deleted']}"
        )

    vault_db.wipe_vault_metadata()
    print("Vault SQLite metadata wiped")

    report = sync_vault(force_hash=True)
    print(
        f"Sync complete: scanned={report.files_scanned} added={report.drift_added} "
        f"modified={report.drift_modified} removed={report.drift_removed}"
    )

    if args.skip_reindex:
        print("Skipping reindex (--skip-reindex)")
        return

    files = vault_db.list_active_files()
    if not files:
        print("No vault files to ingest")
        return

    job_ids: list[tuple[str, str]] = []
    for row in files:
        job_id = enqueue_vault_ingest(row["id"])
        job_ids.append((row["relative_path"], job_id))

    print(f"Enqueued {len(job_ids)} ingest job(s):")
    for rel, job_id in job_ids:
        print(f"  {rel} -> {job_id}")
    print("Ensure api-worker is running: docker compose ps api-worker")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"vault_reset_and_reindex failed: {exc}", file=sys.stderr)
        sys.exit(1)
