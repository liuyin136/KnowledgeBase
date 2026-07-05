"""
scripts/init_neo4j.py — One-time Neo4j schema initialization.

Runs ALL Cypher from neo4j-schema-v1.1.md §3 (constraints + vector indexes
1024-dim cosine + fulltext indexes) against the configured Neo4j instance.
Idempotent (every statement uses `IF NOT EXISTS`).

Usage:
  python scripts/init_neo4j.py

Prints a per-statement status table so the operator can verify success.
"""

from __future__ import annotations

import os
import sys

# Allow running as a script (no package import).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings  # noqa: E402
from app.db.neo4j_client import Neo4jClient  # noqa: E402
from app.db.vector_index import ALL_STATEMENTS, ensure_vector_indexes  # noqa: E402


def main() -> int:
    print(f"[init_neo4j] connecting to {settings.neo4j_uri} as {settings.neo4j_user}", flush=True)
    client = Neo4jClient(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        database=settings.neo4j_database,
    )
    client.verify_connectivity()
    print("[init_neo4j] connectivity verified", flush=True)

    print(f"[init_neo4j] applying {len(ALL_STATEMENTS)} schema statements", flush=True)
    results = ensure_vector_indexes(client.driver, database=settings.neo4j_database)

    print("\n[init_neo4j] results:")
    print(f"  {'kind':<18} {'status':<10} statement")
    print(f"  {'-' * 18} {'-' * 10} {'-' * 60}")
    ok = 0
    failed = 0
    for (kind, stmt), (_kind2, status) in zip(ALL_STATEMENTS, results):
        preview = " ".join(stmt.split())[:80]
        marker = "✓" if status == "ok" else "✗"
        print(f"  {marker} {kind:<16} {status:<10} {preview}")
        if status == "ok":
            ok += 1
        else:
            failed += 1

    print(f"\n[init_neo4j] done: {ok} ok, {failed} failed", flush=True)
    client.close()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
