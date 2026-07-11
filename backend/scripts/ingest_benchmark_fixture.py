"""One-time ingest of hybrid benchmark fixture into Neo4j. Run inside api-worker."""
from __future__ import annotations

import gc
import os
import sys
from pathlib import Path

sys.path.insert(0, "/app/tests")

from hybrid_fixture import (  # type: ignore[import-not-found]
    cleanup_fixture_corpus,
    gold_ids_for_queries,
    ingest_fixture_corpus,
    load_queries,
)


def main() -> None:
    if os.environ.get("ALLOW_BENCHMARK_INGEST") != "1":
        print(
            "Benchmark ingest is blocked by default. Re-run with:\n"
            "  docker compose exec -e ALLOW_BENCHMARK_INGEST=1 api-worker "
            "python scripts/ingest_benchmark_fixture.py",
            file=sys.stderr,
        )
        sys.exit(1)
    data_root = Path(os.environ.get("DATA_ROOT", "/data"))
    cleanup_fixture_corpus()
    chunk_ids = gold_ids_for_queries(load_queries())
    print(f"Ingesting {len(chunk_ids)} benchmark chunks...")
    mapping = ingest_fixture_corpus(data_root, query_rows=load_queries())
    gc.collect()
    print(f"Done. Mapped {len(mapping)} fixture ids.")


if __name__ == "__main__":
    main()
