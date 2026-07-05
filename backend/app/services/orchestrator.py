"""
services/orchestrator.py — PipelineOrchestrator.

STRICT MODULE BOUNDARY (Backend §2):
  • The orchestrator is the ONLY module that:
      - coordinates the pipeline (ChunkingModule → EmbeddingModule → Neo4jClient)
      - emits metadata (via MetadataService)
      - owns transactions + lifecycle (progress events)
      - persists results (:Knowledge, :KnowledgeChunk, :UserQuery, :Memory)
  • It calls the three pure modules + MetadataService + Neo4jClient.
  • It NEVER scores (RetrievalModule does that) — it owns the lifecycle
    of a search run (creates :UserQuery, calls RetrievalModule.hybrid_search,
    persists :Memory nodes). No :Experiment nodes.

Two ingest pipelines:
  • ingest_long_text  — LongText embedding approach. The document is split into
    sliding-window chunks (from settings.longtext_window_tokens, default 30000);
    each window is embedded with the LongText embedding and persisted as a
    :Knowledge node (no child chunks). All windows carry embedding_method="LongText".
  • ingest_child_chunk — ChildChunk embedding approach (USER REQUIREMENT #5):
      1. FIRST embed the FULL document with the LongText embedding → creates ONE
         :Knowledge parent node carrying the long-text vector (the CONTEXT vector).
         Parent's embedding_method="LongText".
      2. THEN chunk the document with the chosen ChildChunk method
         (Recursive / Semantic / Structure-Aware).
      3. THEN embed each child chunk with the ChildChunk embedding method.
      4. Persist BOTH the parent LongText vector AND the child chunk vectors
         (parent-child hierarchy via (:Knowledge)-[:HAS_CHUNK]->(:KnowledgeChunk)).
         Children's embedding_method="ChildChunk".
      5. The ExperimentRun records embedding_approach="ChildChunk" but the
         parent's long-text embedding is ALWAYS present (it's the context).

One search pipeline:
  • run_search — creates :UserQuery (LongText embedding), runs RetrievalModule
    .hybrid_search, persists one :Memory per result.
    (Search-specific metadata lives in SearchMetadata; no :Experiment node.)
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Callable, List, Optional

from app.core.constants import (
    EMBEDDING_METHOD_CHILDCHUNK,
    EMBEDDING_METHOD_LONGTEXT,
    ExperimentStatus,
)
from app.core.exceptions import IngestError, SearchError
from app.core.logging import get_logger, log_pipeline_event
from app.db.neo4j_client import Neo4jClient
from app.models.neo4j_models import (
    Knowledge,
    KnowledgeChunk,
    Memory,
    UserQuery,
)
from app.schemas.experiment import ExperimentRunMetadata
from app.schemas.ingest import ChunkMetadata, IngestProgressEvent
from app.schemas.search import SearchConfig, SearchMetadata, SearchResponse, SearchResult
from app.services.chunking import ChunkBoundary, chunk_long_text, determine_boundaries
from app.services.embedding import EmbeddingModule
from app.services.metadata import (
    CreateChunkMetadataInput,
    CreateExperimentRunInput,
    aggregate_chunk_stats,
    create_chunk_metadata,
    create_experiment_run,
)
from app.services.retrieval import RetrievalModule
from app.utils.timing import now_ms, timed_sync

logger = get_logger("rag.orchestrator")

# Type alias for the progress callback the workers pass in.
ProgressCallback = Callable[[IngestProgressEvent], None]


class PipelineOrchestrator:
    """Owns pipeline coordination, transactions, and lifecycle."""

    def __init__(
        self,
        neo4j: Neo4jClient,
        embedder: EmbeddingModule,
        retrieval: RetrievalModule,
    ) -> None:
        self._neo4j = neo4j
        self._embedder = embedder
        self._retrieval = retrieval

    # ─── INGEST: LongText ───────────────────────────────────────────────────

    async def ingest_long_text(
        self,
        *,
        experiment_id: str,
        source_file: str,
        text: str,
        description: str,
        progress: Optional[ProgressCallback] = None,
    ) -> ExperimentRunMetadata:
        """LongText ingest pipeline.

        1. Split document into sliding windows (config longtext_window_tokens, 10% overlap).
        2. For each window: embed (Jina v5: task="retrieval") + persist as :Knowledge node.
        3. Emit per-window ChunkMetadata via the progress callback.
        4. Build run metadata (no :Experiment node).
        """
        t0 = now_ms()
        total_tokens = self._embedder.token_count(text)

        log_pipeline_event(
            logger,
            "ingest.long_text.start",
            f"LongText ingest started: {source_file} ({total_tokens} tokens)",
            experiment_id=experiment_id,
            source_file=source_file,
        )

        try:
            # 1. Chunking (pure boundary detection — no embedding here)
            if progress:
                progress(IngestProgressEvent(index=0, total=0, progress=0.0, chunk=None, stage="chunking"))
            chunk_boundaries, chunking_ms = timed_sync(lambda: chunk_long_text(text))
            total = len(chunk_boundaries)
            if total == 0:
                raise IngestError(
                    "Document produced no chunks (empty text?)",
                    details={"source_file": source_file},
                    stage="chunking",
                    experiment_id=experiment_id,
                )

            # 2. Embed each window (LongText) + persist as :Knowledge
            chunk_metas: List[ChunkMetadata] = []
            for i, b in enumerate(chunk_boundaries):
                if progress:
                    progress(
                        IngestProgressEvent(
                            index=i,
                            total=total,
                            progress=(i / total) * 100.0,
                            chunk=None,
                            stage="embedding",
                            message=f"Embedding window {i + 1}/{total}",
                        )
                    )
                # Embed (with retry). Documents/passages (ingestion).
                # Jina v5 only: task="retrieval" (via SentenceTransformer)
                vector, embed_ms = timed_sync(
                    lambda b=b: self._embedder.embed_with_retry(
                        b.text, is_query=False
                    )
                )
                # Persist
                if progress:
                    progress(
                        IngestProgressEvent(
                            index=i,
                            total=total,
                            progress=(i / total) * 100.0,
                            chunk=None,
                            stage="persisting",
                            message=f"Persisting window {i + 1}/{total}",
                        )
                    )
                knowledge_id = str(uuid.uuid4())
                knowledge = Knowledge(
                    id=knowledge_id,
                    source_file=source_file,
                    total_tokens=b.token_count,
                    embedding_method=EMBEDDING_METHOD_LONGTEXT,
                    created_at=datetime.utcnow(),
                    vector=vector,
                    text=b.text,
                    chunk_index=b.index,
                    char_start=b.char_start,
                    char_end=b.char_end,
                )
                self._neo4j.create_knowledge(knowledge)

                cm = create_chunk_metadata(
                    CreateChunkMetadataInput(
                        chunk_id=knowledge_id,
                        parent_doc_id=knowledge_id,  # LongText: window IS its own parent
                        chunk_index=b.index,
                        chunk_method=EMBEDDING_METHOD_LONGTEXT,
                        embedding_method=EMBEDDING_METHOD_LONGTEXT,
                        token_count=b.token_count,
                        chunking_time_ms=chunking_ms / max(total, 1),  # amortized
                        embedding_time_ms=embed_ms,
                        char_start=b.char_start,
                        char_end=b.char_end,
                        text=b.text,
                    )
                )
                chunk_metas.append(cm)
                if progress:
                    progress(
                        IngestProgressEvent(
                            index=i + 1,
                            total=total,
                            progress=((i + 1) / total) * 100.0,
                            chunk=cm,
                            stage="embedding",
                            message=f"Window {i + 1}/{total} embedded",
                        )
                    )

            # 3. Aggregate stats + build run metadata (no :Experiment node update)
            stats = aggregate_chunk_stats(chunk_metas)
            total_ms = now_ms() - t0
            run = create_experiment_run(
                CreateExperimentRunInput(
                    experiment_id=experiment_id,
                    description=description,
                    embedding_approach=EMBEDDING_METHOD_LONGTEXT,
                    chunk_method=EMBEDDING_METHOD_LONGTEXT,
                    total_chunks=stats["totalChunks"],
                    avg_tokens_per_chunk=stats["avgTokens"],
                    total_time_ms=total_ms,
                    source_file=source_file,
                    status=ExperimentStatus.COMPLETED.value,
                )
            )
            if progress:
                progress(
                    IngestProgressEvent(
                        index=total,
                        total=total,
                        progress=100.0,
                        chunk=None,
                        stage="done",
                        message=f"Ingested {total} windows",
                    )
                )
            log_pipeline_event(
                logger,
                "ingest.long_text.done",
                f"LongText ingest completed: {total} windows in {total_ms:.1f}ms",
                experiment_id=experiment_id,
                total_chunks=total,
                total_ms=total_ms,
            )
            return run
        except Exception as exc:
            # Log failure (no :Experiment node)
            self._mark_experiment_failed(experiment_id, exc, t0)
            if progress:
                progress(
                    IngestProgressEvent(
                        index=0,
                        total=0,
                        progress=0.0,
                        chunk=None,
                        stage="error",
                        message=str(exc),
                    )
                )
            if isinstance(exc, (IngestError,)):
                raise
            raise IngestError(
                f"LongText ingest failed: {exc}",
                stage="ingest_long_text",
                experiment_id=experiment_id,
            ) from exc

    # ─── INGEST: ChildChunk (USER REQUIREMENT #5) ───────────────────────────

    async def ingest_child_chunk(
        self,
        *,
        experiment_id: str,
        source_file: str,
        text: str,
        chunk_method: str,
        description: str,
        progress: Optional[ProgressCallback] = None,
    ) -> ExperimentRunMetadata:
        """ChildChunk ingest pipeline (USER REQUIREMENT #5).

        ChildChunk = LongText parent embedding + N child chunk embeddings.

        Step 1: Embed the FULL document with the LongText embedding → create
                ONE :Knowledge parent node carrying the long-text vector (the
                CONTEXT vector). Parent's embedding_method="LongText".
        Step 2: Chunk the document (Recursive / Semantic / Structure-Aware).
        Step 3: Embed each child chunk with the ChildChunk embedding method.
        Step 4: Persist BOTH the parent LongText vector AND the child chunk
                vectors. Children's embedding_method="ChildChunk".
        Step 5: The ExperimentRun records embedding_approach="ChildChunk" but
                the parent's long-text embedding is ALWAYS present.

        The parent LongText vector is the context; child vectors are the
        retrieval targets (the HNSW index on :KnowledgeChunk serves them).
        """
        t0 = now_ms()
        total_tokens = self._embedder.token_count(text)

        log_pipeline_event(
            logger,
            "ingest.child_chunk.start",
            f"ChildChunk ingest started: {source_file} ({total_tokens} tokens, method={chunk_method})",
            experiment_id=experiment_id,
            source_file=source_file,
            chunk_method=chunk_method,
        )

        try:
            # ─── STEP 1: LongText parent embedding (the context vector) ──────
            # The parent is the FULL document treated as a PASSAGE (ingestion).
            # Uses Jina v5 encode: task="retrieval" (via SentenceTransformer)
            if progress:
                progress(
                    IngestProgressEvent(
                        index=0,
                        total=0,
                        progress=0.0,
                        chunk=None,
                        stage="embedding",
                        message="Embedding full document with LongText (parent context vector)",
                    )
                )
            parent_vector, parent_embed_ms = timed_sync(
                lambda: self._embedder.embed_with_retry(
                    text, is_query=False
                )
            )
            parent_id = str(uuid.uuid4())
            parent = Knowledge(
                id=parent_id,
                source_file=source_file,
                total_tokens=total_tokens,
                embedding_method=EMBEDDING_METHOD_LONGTEXT,  # ← parent ALWAYS LongText
                created_at=datetime.utcnow(),
                vector=parent_vector,
                text=text,  # ← full document text (context for retrieval)
                chunk_index=0,
                char_start=0,
                char_end=len(text),
            )
            self._neo4j.create_knowledge(parent)
            log_pipeline_event(
                logger,
                "ingest.child_chunk.parent_embedded",
                f"Parent LongText vector created (dim={len(parent_vector)})",
                experiment_id=experiment_id,
                parent_id=parent_id,
                embed_ms=parent_embed_ms,
            )

            # ─── STEP 2: Chunk the document (Recursive / Semantic / Structure-Aware) ──
            if progress:
                progress(
                    IngestProgressEvent(
                        index=0,
                        total=0,
                        progress=0.0,
                        chunk=None,
                        stage="chunking",
                        message=f"Chunking with {chunk_method}",
                    )
                )
            chunk_boundaries, chunking_ms = timed_sync(
                lambda: determine_boundaries(text, chunk_method)
            )
            total = len(chunk_boundaries)
            if total == 0:
                raise IngestError(
                    "Document produced no child chunks (empty text?)",
                    details={"source_file": source_file, "chunk_method": chunk_method},
                    stage="chunking",
                    experiment_id=experiment_id,
                )

            # ─── STEP 3 + 4: Embed each child chunk + persist with HAS_CHUNK edge ──
            chunk_metas: List[ChunkMetadata] = []
            for i, b in enumerate(chunk_boundaries):
                if progress:
                    progress(
                        IngestProgressEvent(
                            index=i,
                            total=total,
                            progress=(i / total) * 100.0,
                            chunk=None,
                            stage="embedding",
                            message=f"Embedding child chunk {i + 1}/{total}",
                        )
                    )
                # Embed each child chunk as a PASSAGE (ingestion).
                # Jina v5: task="retrieval" (via SentenceTransformer)
                child_vector, child_embed_ms = timed_sync(
                    lambda b=b: self._embedder.embed_with_retry(
                        b.text, is_query=False
                    )
                )
                if progress:
                    progress(
                        IngestProgressEvent(
                            index=i,
                            total=total,
                            progress=(i / total) * 100.0,
                            chunk=None,
                            stage="persisting",
                            message=f"Persisting child chunk {i + 1}/{total}",
                        )
                    )
                chunk_id = str(uuid.uuid4())
                knowledge_chunk = KnowledgeChunk(
                    id=chunk_id,
                    parent_doc_id=parent_id,
                    chunk_index=b.index,
                    text=b.text,
                    token_count=b.token_count,
                    chunk_method=chunk_method,
                    chunking_time_ms=chunking_ms / max(total, 1),  # amortized across chunks
                    embedding_time_ms=child_embed_ms,
                    embedding_method=EMBEDDING_METHOD_CHILDCHUNK,  # ← children ALWAYS ChildChunk
                    vector=child_vector,
                    char_start=b.char_start,
                    char_end=b.char_end,
                    section=b.section,
                )
                self._neo4j.create_chunk(knowledge_chunk, parent_knowledge_id=parent_id)

                cm = create_chunk_metadata(
                    CreateChunkMetadataInput(
                        chunk_id=chunk_id,
                        parent_doc_id=parent_id,
                        chunk_index=b.index,
                        chunk_method=chunk_method,
                        embedding_method=EMBEDDING_METHOD_CHILDCHUNK,
                        token_count=b.token_count,
                        chunking_time_ms=chunking_ms / max(total, 1),
                        embedding_time_ms=child_embed_ms,
                        char_start=b.char_start,
                        char_end=b.char_end,
                        section=b.section,
                        text=b.text,
                    )
                )
                chunk_metas.append(cm)
                if progress:
                    progress(
                        IngestProgressEvent(
                            index=i + 1,
                            total=total,
                            progress=((i + 1) / total) * 100.0,
                            chunk=cm,
                            stage="embedding",
                            message=f"Child chunk {i + 1}/{total} embedded",
                        )
                    )

            # ─── STEP 5: Aggregate stats + build run metadata (no :Experiment node) ─
            stats = aggregate_chunk_stats(chunk_metas)
            total_ms = now_ms() - t0
            run = create_experiment_run(
                CreateExperimentRunInput(
                    experiment_id=experiment_id,
                    description=description,
                    embedding_approach=EMBEDDING_METHOD_CHILDCHUNK,
                    chunk_method=chunk_method,
                    total_chunks=stats["totalChunks"],
                    avg_tokens_per_chunk=stats["avgTokens"],
                    total_time_ms=total_ms,
                    source_file=source_file,
                    status=ExperimentStatus.COMPLETED.value,
                )
            )
            if progress:
                progress(
                    IngestProgressEvent(
                        index=total,
                        total=total,
                        progress=100.0,
                        chunk=None,
                        stage="done",
                        message=f"Ingested 1 parent + {total} child chunks",
                    )
                )
            log_pipeline_event(
                logger,
                "ingest.child_chunk.done",
                f"ChildChunk ingest completed: 1 parent (LongText) + {total} children in {total_ms:.1f}ms",
                experiment_id=experiment_id,
                total_chunks=total,
                parent_id=parent_id,
                total_ms=total_ms,
            )
            return run
        except Exception as exc:
            # Log failure (no :Experiment node)
            self._mark_experiment_failed(experiment_id, exc, t0)
            if progress:
                progress(
                    IngestProgressEvent(
                        index=0,
                        total=0,
                        progress=0.0,
                        chunk=None,
                        stage="error",
                        message=str(exc),
                    )
                )
            if isinstance(exc, (IngestError,)):
                raise
            raise IngestError(
                f"ChildChunk ingest failed: {exc}",
                stage="ingest_child_chunk",
                experiment_id=experiment_id,
            ) from exc

    # ─── SEARCH ─────────────────────────────────────────────────────────────

    async def run_search(
        self,
        *,
        search_id: str,
        experiment_id: str,
        raw_query: str,
        config: SearchConfig,
        progress: Optional[ProgressCallback] = None,
    ) -> SearchResponse:
        """Search pipeline.

        1. Embed the query with LongText embedding → :UserQuery node.
        2. Call RetrievalModule.hybrid_search (vector + optional BM25 +
           manual/adaptive fusion + optional reranker) — scoring only.
        3. Persist one :Memory per result (links :UserQuery → :Memory → :KnowledgeChunk).
        4. (No :Experiment node update; search metadata returned to caller.)
        """
        t0 = now_ms()

        log_pipeline_event(
            logger,
            "search.start",
            f"Search started: {raw_query[:80]}",
            experiment_id=experiment_id,
            search_id=search_id,
            config=config.model_dump(),
        )

        try:
            # 1. Embed the query as a SEARCH QUERY.
            #    Jina v5: task="retrieval" (via SentenceTransformer)
            if progress:
                progress(
                    IngestProgressEvent(
                        index=0, total=1, progress=0.0, chunk=None, stage="embedding",
                        message="Embedding query",
                    )
                )
            query_vector, query_embed_ms = timed_sync(
                lambda: self._embedder.embed_with_retry(
                    raw_query, is_query=True
                )
            )
            user_query_id = str(uuid.uuid4())
            user_query = UserQuery(
                id=user_query_id,
                text=raw_query,
                total_tokens=self._embedder.token_count(raw_query),
                embedding_method=EMBEDDING_METHOD_LONGTEXT,
                created_at=datetime.utcnow(),
                vector=query_vector,
            )
            self._neo4j.create_user_query(user_query)

            # 2. Hybrid search (scoring only — RetrievalModule NEVER persists)
            results, metadata = self._retrieval.hybrid_search(
                query_text=raw_query,
                query_vector=query_vector,
                config=config,
            )
            # Fill in the orchestrator-owned fields:
            metadata.searchId = search_id
            metadata.experimentId = experiment_id
            metadata.queryEmbeddingTimeMs = round(query_embed_ms, 3)
            # Recompute total to include query embed time
            metadata.totalSearchTimeMs = round(now_ms() - t0, 3)

            # 3. Persist :Memory for each result (orchestrator owns transactions)
            for r in results:
                memory = Memory(
                    id=str(uuid.uuid4()),
                    user_query_id=user_query_id,
                    timestamp=datetime.utcnow(),
                    success_score=None,
                    notes=None,
                    query_text=raw_query,
                    chunk_id=r.chunkId,
                    chunk_text=r.text,
                    score=r.finalScore,
                    vector_score=r.vectorScore,
                    bm25_score=r.bm25Score,
                    fused_score=r.fusedScore,
                    reranker_score=r.rerankerScore,
                )
                self._neo4j.create_memory(memory)

            # no experiment node update (removed)
            total_ms = now_ms() - t0

            if progress:
                progress(
                    IngestProgressEvent(
                        index=1,
                        total=1,
                        progress=100.0,
                        chunk=None,
                        stage="done",
                        message=f"Search completed: {len(results)} results",
                    )
                )
            log_pipeline_event(
                logger,
                "search.done",
                f"Search completed: {len(results)} results in {total_ms:.1f}ms",
                experiment_id=experiment_id,
                search_id=search_id,
                result_count=len(results),
                best_alpha=metadata.bestAlpha,
                total_ms=total_ms,
            )
            return SearchResponse(searchId=search_id, results=results, metadata=metadata)
        except Exception as exc:
            self._mark_experiment_failed(experiment_id, exc, t0)
            if progress:
                progress(
                    IngestProgressEvent(
                        index=0, total=0, progress=0.0, chunk=None, stage="error",
                        message=str(exc),
                    )
                )
            if isinstance(exc, (SearchError,)):
                raise
            raise SearchError(
                f"Search failed: {exc}",
                stage="search",
                experiment_id=experiment_id,
            ) from exc

    # ─── internal ───────────────────────────────────────────────────────────

    def _mark_experiment_failed(self, experiment_id: str, exc: Exception, t0: float) -> None:
        """Log failure for a run (no :Experiment node; experiment_id is correlation only)."""
        from app.core.exceptions import RAGBaseException
        from app.core.logging import log_pipeline_error

        err_code = exc.code if isinstance(exc, RAGBaseException) else "INTERNAL_ERROR"
        err_msg = str(exc)[:2000]
        log_pipeline_error(
            logger,
            stage=getattr(exc, "stage", "unknown") or "unknown",
            error_code=err_code,
            error_message=err_msg,
            experiment_id=experiment_id,
            retry_count=getattr(exc, "retry_count", None),
        )
