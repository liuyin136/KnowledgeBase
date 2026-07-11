"""Helpers for GPU hybrid search integration benchmarks."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
BENCHMARK_PREFIX = "_benchmark/hybrid_fixture"


def load_corpus() -> list[dict]:
    data = json.loads((FIXTURES / "hybrid_corpus.json").read_text(encoding="utf-8"))
    return data["chunks"]


def load_queries() -> list[dict]:
    lines = (FIXTURES / "hybrid_20chunks.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def gpu_integration_available() -> bool:
    if os.environ.get("SKIP_GPU_INTEGRATION") == "1":
        return False
    # Ephemeral `docker compose run` containers contend for GPU with the long-running worker.
    if os.environ.get("IN_WORKER_EXEC") != "1" and os.path.exists("/.dockerenv"):
        try:
            with open("/proc/1/cgroup", encoding="utf-8") as f:
                cgroup = f.read()
            if "api-worker-run" in cgroup:
                return False
        except OSError:
            pass
    try:
        from app.services.neo4j_client import get_neo4j_client

        get_neo4j_client().verify_connectivity()
    except Exception:
        return False
    try:
        subprocess.run(["nvidia-smi"], capture_output=True, check=True, timeout=10)
        return True
    except Exception:
        return False


def models_available() -> bool:
    model_root = Path(os.environ.get("MODEL_PATH", "/app/models"))
    retrieval = model_root / "jina/retrieval/jina-embeddings-v5-omni-small-retrieval-F16.gguf"
    reranker = model_root / "jina/reranker/jina-reranker-v3-BF16.gguf"
    return retrieval.is_file() and reranker.is_file()


def write_fixture_files(data_root: Path, chunk_ids: set[str] | None = None) -> list[str]:
    """Write one file per corpus chunk so ingest maps 1:1 to fixture ids."""
    paths: list[str] = []
    for row in load_corpus():
        if chunk_ids is not None and row["id"] not in chunk_ids:
            continue
        rel = f"{BENCHMARK_PREFIX}/{row['id']}.md"
        full = data_root / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(row["content"], encoding="utf-8")
        paths.append(rel)
    return paths


def gold_ids_for_queries(query_rows: list[dict] | None = None) -> set[str]:
    rows = query_rows or load_queries()
    ids: set[str] = set()
    for row in rows:
        ids.update(row["gold_chunk_ids"])
    return ids


def ingest_fixture_corpus(
    data_root: Path,
    *,
    query_rows: list[dict] | None = None,
) -> dict[str, str]:
    """Ingest benchmark files; return fixture_id → neo4j chunk_id map."""
    import gc

    from app.services.ingest_guard import benchmark_ingest_allowed
    from app.workers.tasks import ingest_document

    if not benchmark_ingest_allowed():
        raise RuntimeError(
            "Benchmark ingest is blocked. Set ALLOW_BENCHMARK_INGEST=1, e.g. "
            "docker compose exec -e ALLOW_BENCHMARK_INGEST=1 api-worker "
            "python scripts/ingest_benchmark_fixture.py"
        )

    chunk_ids = gold_ids_for_queries(query_rows)
    paths = write_fixture_files(data_root, chunk_ids)
    for rel in paths:
        ingest_document(rel)
        gc.collect()

    from app.services.neo4j_client import get_neo4j_client

    client = get_neo4j_client()
    fixture_to_neo4j: dict[str, str] = {}
    for fid in chunk_ids:
        rel = f"{BENCHMARK_PREFIX}/{fid}.md"
        existing = client.get_existing_chunks(rel)
        if existing:
            fixture_to_neo4j[fid] = existing[0]["id"]
    return fixture_to_neo4j


def existing_fixture_map(chunk_ids: set[str] | None = None) -> dict[str, str]:
    """Map fixture ids to Neo4j chunk ids for already-ingested benchmark files."""
    from app.services.neo4j_client import get_neo4j_client

    ids = chunk_ids or gold_ids_for_queries()
    client = get_neo4j_client()
    mapping: dict[str, str] = {}
    for fid in ids:
        rel = f"{BENCHMARK_PREFIX}/{fid}.md"
        existing = client.get_existing_chunks(rel)
        if existing:
            mapping[fid] = existing[0]["id"]
    return mapping


def cleanup_fixture_corpus() -> None:
    from app.services.neo4j_client import get_neo4j_client

    get_neo4j_client().delete_knowledge_by_prefix(f"{BENCHMARK_PREFIX}/")
