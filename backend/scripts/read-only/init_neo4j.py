"""Apply pre-phase Neo4j schema DDL."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from neo4j import GraphDatabase


def main() -> None:
    uri = os.environ.get("NEO4J_URI", "bolt://neo4j:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "P@ssw0rd")
    schema_path = Path(__file__).resolve().parent.parent / "init_schema.cypher"
    ddl = schema_path.read_text(encoding="utf-8")

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            result = session.run("RETURN 1 AS n").single()
            print(f"Neo4j OK: {result['n']}")
            for statement in _split_cypher(ddl):
                session.run(statement).consume()
                print(f"Applied: {statement.split()[0:3]}...")
    finally:
        driver.close()


def _split_cypher(text: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        buf.append(line)
        if stripped.endswith(";"):
            parts.append("\n".join(buf).rstrip(";").strip())
            buf = []
    if buf:
        parts.append("\n".join(buf).strip())
    return parts


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Neo4j init failed: {exc}", file=sys.stderr)
        sys.exit(1)
