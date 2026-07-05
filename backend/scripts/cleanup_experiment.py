"""
scripts/cleanup_experiment.py — One-time cleanup to remove :Experiment nodes and label.

This removes all remaining :Experiment nodes (and their relationships) from Neo4j,
and drops the old uniqueness constraint.

Safe to run multiple times. After this, the code no longer creates :Experiment.

Usage (from project root, via docker or directly):
  docker compose run --rm backend python scripts/cleanup_experiment.py
  # or inside backend container:
  python scripts/cleanup_experiment.py

Prints before/after counts and status.
"""

from __future__ import annotations

import os
import sys

# Allow running as a script (no package import).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from neo4j import Driver

from app.core.config import settings  # noqa: E402
from app.db.neo4j_client import Neo4jClient  # noqa: E402


def main() -> int:
    print(f"[cleanup_experiment] connecting to {settings.neo4j_uri} as {settings.neo4j_user}", flush=True)
    client = Neo4jClient(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        database=settings.neo4j_database,
    )
    client.verify_connectivity()
    print("[cleanup_experiment] connectivity verified", flush=True)

    driver: Driver = client.driver
    db = settings.neo4j_database or "neo4j"

    with driver.session(database=db) as session:
        # 1. Count before
        before = session.run("MATCH (e:Experiment) RETURN count(e) AS c").single()["c"]
        print(f"[cleanup_experiment] :Experiment nodes before: {before}", flush=True)

        if before > 0:
            # 2. Delete all :Experiment nodes + relationships
            session.run("MATCH (e:Experiment) DETACH DELETE e").consume()
            after_delete = session.run("MATCH (e:Experiment) RETURN count(e) AS c").single()["c"]
            print(f"[cleanup_experiment] deleted nodes, remaining :Experiment: {after_delete}", flush=True)
        else:
            print("[cleanup_experiment] no :Experiment nodes found", flush=True)

        # 3. Drop old constraint(s) — the one we used to create was named "experiment_id"
        #    Use IF EXISTS for safety (Neo4j 5+ supports it).
        try:
            session.run("DROP CONSTRAINT experiment_id IF EXISTS").consume()
            print("[cleanup_experiment] dropped constraint 'experiment_id' (if existed)", flush=True)
        except Exception as exc:
            print(f"[cleanup_experiment] note: could not drop 'experiment_id' constraint: {exc}", flush=True)

        # Also try to find and drop any other Experiment-related constraints
        try:
            rows = session.run(
                "SHOW CONSTRAINTS YIELD name, labelsOrTypes "
                "WHERE any(l IN labelsOrTypes WHERE l = 'Experiment') "
                "RETURN name"
            ).data()
            for row in rows:
                name = row["name"]
                try:
                    session.run(f"DROP CONSTRAINT `{name}` IF EXISTS").consume()
                    print(f"[cleanup_experiment] dropped additional constraint: {name}", flush=True)
                except Exception:
                    pass
        except Exception:
            pass  # SHOW CONSTRAINTS may vary slightly by version

        # 4. Final verification
        remaining = session.run("MATCH (e:Experiment) RETURN count(e) AS c").single()["c"]
        constraints = session.run(
            "SHOW CONSTRAINTS YIELD name, labelsOrTypes "
            "RETURN name, labelsOrTypes"
        ).data()

        exp_constraints = [
            c for c in constraints
            if any(str(l).lower() == "experiment" for l in (c.get("labelsOrTypes") or []))
        ]

        print(f"\n[cleanup_experiment] remaining :Experiment nodes: {remaining}")
        print(f"[cleanup_experiment] remaining Experiment constraints: {len(exp_constraints)}")
        if exp_constraints:
            for c in exp_constraints:
                print(f"  - {c}")

        print("[cleanup_experiment] done. :Experiment label should be gone from active data.", flush=True)

    client.close()
    return 0 if remaining == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
