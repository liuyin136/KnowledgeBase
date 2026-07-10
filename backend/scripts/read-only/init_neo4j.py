"""Verify Neo4j connectivity (baseline stub)."""
from __future__ import annotations

import os
import sys

from neo4j import GraphDatabase


def main() -> None:
    uri = os.environ.get("NEO4J_URI", "bolt://neo4j:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "P@ssw0rd")
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            result = session.run("RETURN 1 AS n").single()
            print(f"Neo4j OK: {result['n']}")
    finally:
        driver.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Neo4j init failed: {exc}", file=sys.stderr)
        sys.exit(1)
