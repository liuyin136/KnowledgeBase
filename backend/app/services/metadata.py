"""
services/metadata.py — MetadataService.

STRICT MODULE BOUNDARY (Backend §2):
  • PURE factory functions for standardized metadata. NEVER persists, NEVER
    embeds, NEVER coordinates. Called by the PipelineOrchestrator.
  • Mirrors src/lib/rag/metadata.ts (createChunkMetadata / createExperimentRun
    / aggregateChunkStats) so the FastAPI backend emits identical metadata
    shapes.

Per Backend §6, every run produces:
  • ChunkMetadata  (chunk_id, parent_doc_id, chunk_method, embedding_method,
                    token_count, timings, experiment_id, char range, section,
                    text preview)
  • ExperimentRun  (experiment_id, description, embedding_approach, chunk_method,
                    total_chunks, avg_tokens, total_time_ms, source_file, status)
"""

from __future__ import annotations

from typing import Iterable, List, Optional

from app.schemas.ingest import ChunkMetadata
from app.schemas.experiment import ExperimentRunMetadata
from app.utils.tokenization import preview


class CreateChunkMetadataInput:
    """Input bundle for create_chunk_metadata (kept as a simple class for clarity)."""

    def __init__(
        self,
        *,
        chunk_id: str,
        parent_doc_id: str,
        experiment_id: str,
        chunk_index: int,
        chunk_method: str,
        embedding_method: str,
        token_count: int,
        chunking_time_ms: float,
        embedding_time_ms: float,
        char_start: Optional[int] = None,
        char_end: Optional[int] = None,
        section: Optional[str] = None,
        text: str,
    ) -> None:
        self.chunk_id = chunk_id
        self.parent_doc_id = parent_doc_id
        self.experiment_id = experiment_id
        self.chunk_index = chunk_index
        self.chunk_method = chunk_method
        self.embedding_method = embedding_method
        self.token_count = token_count
        self.chunking_time_ms = chunking_time_ms
        self.embedding_time_ms = embedding_time_ms
        self.char_start = char_start
        self.char_end = char_end
        self.section = section
        self.text = text


def create_chunk_metadata(inp: CreateChunkMetadataInput) -> ChunkMetadata:
    """Create a ChunkMetadata record (pure — no side effects)."""
    return ChunkMetadata(
        chunkId=inp.chunk_id,
        parentDocId=inp.parent_doc_id,
        experimentId=inp.experiment_id,
        chunkIndex=inp.chunk_index,
        chunkMethod=inp.chunk_method,
        embeddingMethod=inp.embedding_method,
        tokenCount=inp.token_count,
        chunkingTimeMs=round(inp.chunking_time_ms, 3),
        embeddingTimeMs=round(inp.embedding_time_ms, 3),
        charStart=inp.char_start,
        charEnd=inp.char_end,
        section=inp.section,
        textPreview=preview(inp.text, 220),
    )


class CreateExperimentRunInput:
    def __init__(
        self,
        *,
        experiment_id: str,
        description: str,
        embedding_approach: str,
        chunk_method: str,
        total_chunks: int,
        avg_tokens_per_chunk: float,
        total_time_ms: float,
        source_file: str,
        status: str,
    ) -> None:
        self.experiment_id = experiment_id
        self.description = description
        self.embedding_approach = embedding_approach
        self.chunk_method = chunk_method
        self.total_chunks = total_chunks
        self.avg_tokens_per_chunk = avg_tokens_per_chunk
        self.total_time_ms = total_time_ms
        self.source_file = source_file
        self.status = status


def create_experiment_run(inp: CreateExperimentRunInput) -> ExperimentRunMetadata:
    """Create an ExperimentRun metadata record (pure)."""
    return ExperimentRunMetadata(
        experimentId=inp.experiment_id,
        description=inp.description,
        embeddingApproach=inp.embedding_approach,
        chunkMethod=inp.chunk_method,
        totalChunks=inp.total_chunks,
        avgTokensPerChunk=round(inp.avg_tokens_per_chunk, 2),
        totalTimeMs=round(inp.total_time_ms, 3),
        sourceFile=inp.source_file,
        status=inp.status,
    )


def aggregate_chunk_stats(
    chunks: Iterable,
) -> dict:
    """Compute aggregate stats from a list of chunk metadatas.

    Accepts any object with `.token_count`, `.chunking_time_ms`, `.embedding_time_ms`
    (ChunkMetadata, KnowledgeChunk, or dict-like via attribute access).
    """
    materialized: List = list(chunks)
    total_chunks = len(materialized)
    if total_chunks == 0:
        return {
            "totalChunks": 0,
            "avgTokens": 0.0,
            "totalChunkingMs": 0.0,
            "totalEmbeddingMs": 0.0,
        }
    total_tokens = 0
    total_chunking = 0.0
    total_embedding = 0.0
    for c in materialized:
        total_tokens += getattr(c, "token_count", 0) or 0
        total_chunking += getattr(c, "chunking_time_ms", 0.0) or 0.0
        total_embedding += getattr(c, "embedding_time_ms", 0.0) or 0.0
    return {
        "totalChunks": total_chunks,
        "avgTokens": total_tokens / total_chunks,
        "totalChunkingMs": total_chunking,
        "totalEmbeddingMs": total_embedding,
    }
