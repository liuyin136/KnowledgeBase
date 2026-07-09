"""RQ task functions executed by api-worker."""
from __future__ import annotations

import os
from pathlib import Path

from neo4j import GraphDatabase


def index_log_file(relative_path: str) -> dict[str, str | float | bool]:
    data_root = Path(os.environ.get("DATA_ROOT", "/data"))
    file_path = data_root / relative_path
    if not file_path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    parts = relative_path.split("/", 1)
    category = parts[0] if parts else "unknown"
    title = file_path.stem
    mtime = file_path.stat().st_mtime

    uri = os.environ.get("NEO4J_URI", "bolt://neo4j:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "P@ssw0rd")

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            session.run(
                """
                MERGE (f:LogFile {path: $path})
                SET f.category = $category,
                    f.title = $title,
                    f.mtime = $mtime
                """,
                path=relative_path,
                category=category,
                title=title,
                mtime=mtime,
            )
    finally:
        driver.close()

    return {"path": relative_path, "indexed": True}
