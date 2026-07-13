"""Phase 1.7 one-time reset: purge Neo4j vault ingestion and mark all files not_indexed.

Usage (from project root):

  docker compose run --rm api-worker python scripts/vault_reset_to_not_indexed.py --dry-run
  docker compose run --rm api-worker python scripts/vault_reset_to_not_indexed.py
"""
from __future__ import annotations

import argparse
import sys

from app.services import vault_db
from app.services.neo4j_client import get_neo4j_client
from app.services.vault_migration import clear_migration_redis_caches, known_vault_sources


def run_reset(*, dry_run: bool = False) -> dict[str, int | str]:
    vault_db.init_vault_db()
    sources = known_vault_sources()
    active = vault_db.list_active_files()

    if dry_run:
        return {
            "dry_run": True,
            "source_count": len(sources),
            "file_count": len(active),
        }

    neo = get_neo4j_client()
    neo_stats = neo.delete_all_vault_ingestion(sources) if sources else {}
    redis_deleted = clear_migration_redis_caches()

    with vault_db.get_connection() as conn:
        conn.execute(
            """
            UPDATE vault_files
            SET index_status = 'not_indexed',
                chunk_count = 0,
                ingest_lock_job_id = NULL,
                last_ingest_job_id = NULL,
                last_ingest_at = NULL,
                error_message = NULL
            WHERE index_status != 'deleted'
            """
        )
        conn.commit()

    return {
        "dry_run": False,
        "source_count": len(sources),
        "file_count": len(active),
        "neo4j_stats": neo_stats,
        "redis_keys_deleted": redis_deleted,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset vault files to not_indexed and purge Neo4j ingestion.")
    parser.add_argument("--dry-run", action="store_true", help="Print counts only")
    args = parser.parse_args()
    result = run_reset(dry_run=args.dry_run)
    print(result)
    if result.get("dry_run"):
        sys.exit(0)
    sys.exit(0)


if __name__ == "__main__":
    main()
