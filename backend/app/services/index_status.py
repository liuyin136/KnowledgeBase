from __future__ import annotations

from app.core.logging import get_logger
from app.models.file_schemas import FileListItem
from app.services.ingest_status import resolve_index_status
from app.services.neo4j_client import get_neo4j_client

logger = get_logger("rag.index_status")


def enrich_files_with_index_status(files: list[FileListItem]) -> list[FileListItem]:
    if not files:
        return files
    client = get_neo4j_client()
    enriched: list[FileListItem] = []
    for item in files:
        knowledge = client.get_knowledge_by_source(item.path)
        meta = resolve_index_status(item.path, neo4j_knowledge=knowledge)
        enriched.append(
            item.model_copy(
                update={
                    "index_status": meta["index_status"],
                    "indexed_at": meta.get("indexed_at"),
                    "last_ingest_job_id": meta.get("last_ingest_job_id"),
                    "chunk_count": int(meta.get("chunk_count") or 0),
                }
            )
        )
    return enriched
