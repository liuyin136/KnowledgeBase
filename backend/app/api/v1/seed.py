"""
api/v1/seed.py — Seed sample markdown documents into Neo4j.

  • POST /api/v1/seed → {created, skipped, createdIds}

Seeds 4 sample markdown documents about RAG / hybrid-search / embeddings /
experiment-design — the same conceptual content the v1 sandbox seeded (so the
Dashboard's "Seed sample docs" button produces equivalent starting state on
the FastAPI backend).

Idempotent: if a :Knowledge node with the same source_file already exists
(for the pseudo "upload" experiment_id), it is skipped.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends

from app.api.dependencies import get_db
from app.db.neo4j_client import Neo4jClient
from app.models.neo4j_models import Knowledge

router = APIRouter(prefix="/seed", tags=["seed"])


# ─── Sample markdown documents (mirrors v1 sandbox seed content) ─────────────

SAMPLE_DOCS = {
    "rag-overview.md": """# Retrieval-Augmented Generation (RAG) — Overview

Retrieval-Augmented Generation (RAG) combines a retriever with a generator.
The retriever surfaces relevant context from a knowledge base; the generator
conditions its output on that context. This reduces hallucination and lets
the system cite sources.

## Why RAG?

- **Freshness**: the knowledge base can be updated without retraining.
- **Citations**: every generated claim can be traced back to a retrieved chunk.
- **Domain adaptation**: a single base model serves many domains via different
  knowledge bases.

## Components

1. **Ingest pipeline**: chunk documents, embed chunks, store in a vector DB.
2. **Query pipeline**: embed the query, retrieve top-K, optionally rerank.
3. **Generation**: feed retrieved context to an LLM.

## Parent-Child Hierarchy

A parent document is the full source (or a large window). Child chunks are
smaller, embedded units retrieved individually. The parent provides context;
the child provides precision. Hybrid search often retrieves child chunks and
expands to the parent for generation.

## Open Challenges

- Chunk-size trade-offs (too small = lost context; too large = diluted signal).
- Embedding-model selection (dense vs sparse, multilingual, long-context).
- Hybrid fusion tuning (vector + BM25 weighting).
- Evaluation: retrieval quality is hard to measure without labeled queries.
""",
    "hybrid-search-deep-dive.md": """# Hybrid Search — Deep Dive

Hybrid search combines dense vector retrieval with sparse lexical retrieval
(typically BM25). The two signals are complementary: vector search captures
semantic similarity; BM25 captures exact-term matches.

## Fusion Strategies

### 1. Weighted fusion (primary for v1.2)

```
fused = alpha * vectorScore + beta * bm25Score
beta = 1 - alpha
```

`alpha` controls the vector/BM25 trade-off. A manual `alpha` lets the
researcher sweep the trade-off space; an **adaptive** sweep tries
`alpha ∈ {0.1, 0.2, ..., 0.9}` and picks the alpha whose TOP-1 result has
the highest fused similarity. The best alpha is returned in the search
metadata for observability.

### 2. Reciprocal Rank Fusion (RRF)

```
score(d) = Σ 1 / (k + rank_i(d))
```

RRF is rank-based (no score normalization). It's a robust alternative when
raw scores are incomparable. Provided as a documented alternative in v1.2;
weighted fusion is primary.

## Score Normalization

Before fusion, both vector and BM25 scores are min-max normalized across the
candidate set so `alpha` has a stable interpretation regardless of the raw
score scales.

## Reranking

A cross-encoder (e.g. BGE-reranker-base) can re-score the top-N fused
candidates. Cross-encoders are slower than bi-encoders but more accurate
for the final ranking. `topNRerank` controls how many candidates are
re-scored; the final ranking uses the reranker score when available.

## Observability

Every search records:
- query embedding time, vector search time, BM25 time, rerank time, total time
- candidates before rerank, results after rerank
- alpha used (and best alpha when adaptive)
- per-result scores: vector, bm25, fused, reranker, final

This lets the researcher systematically compare configurations.
""",
    "embedding-models.md": """# Embedding Models for RAG

The embedding model is the foundation of retrieval quality. v1 standardizes
on **BGE-M3** (1024 dimensions, multilingual, long-context).

## BGE-M3

- **Dimensions**: 1024
- **Multilingual**: 100+ languages, strong CJK performance
- **Long context**: up to 8192 tokens
- **Three embedding types**: dense, sparse (lexical), multi-vector (ColBERT-like)
- v1 uses the **dense** output only

## Hardware Considerations

BGE-M3 fits comfortably in <2GB VRAM. On a GTX 3070 Ti (8GB) it leaves
plenty of headroom for the reranker (BGE-reranker-base, ~280MB).

## Construction Note #1 — float32 Casting

On GPU, sentence-transformers may return bfloat16 tensors. NumPy has no
native bfloat16 dtype and will fail (or silently produce wrong values via
object arrays). Always cast:

```python
vector = embedding.cpu().to(torch.float32).numpy()
```

before returning any vector to callers. This is applied on every encode
path (GPU and CPU) in the EmbeddingModule.

## LongText vs ChildChunk

- **LongText**: embed the whole document (or a large sliding window) as a
  single vector. The window IS the retrieval unit. Good for short docs.
- **ChildChunk**: embed the whole document with LongText (parent context
  vector) AND embed each child chunk (retrieval targets). The parent
  provides context; the child provides precision. This is the foundation
  for parent-child hybrid retrieval.

Both approaches persist a parent `:Knowledge` node carrying the long-text
vector; ChildChunk additionally persists `:KnowledgeChunk` children with
their own vectors.
""",
    "experiment-design.md": """# Experiment Design for RAG Evaluation

A RAG experiment is a controlled comparison of one or more configuration
knobs with everything else held fixed. The platform records every run as an
`:Experiment` node with full observability metadata.

## Independent Variables (knobs)

- **Embedding approach**: LongText vs ChildChunk
- **Chunk method**: Recursive, Semantic, Structure-Aware
- **Chunk size / overlap**: target tokens, overlap tokens
- **Hybrid alpha**: vector vs BM25 weighting (0.0 = pure BM25, 1.0 = pure vector)
- **BM25 on/off**: enables/disables the lexical signal entirely
- **Reranker on/off + top-N**: cross-encoder reranking scope
- **Parent context levels**: how much parent context to expand to
- **Adaptive auto-tune**: let the system pick the best alpha per query

## Dependent Variables (metrics)

- Retrieval quality: top-K relevance (needs labeled queries — manual in v1)
- Per-stage timings: chunking, embedding, vector search, BM25, rerank
- Throughput: docs/sec (ingest), queries/sec (search)
- Failure modes: which configs fail (e.g. CUDA OOM with large batches)

## Methodology

1. Fix a corpus (e.g. the 4 sample markdown docs).
2. Run ingest with configuration A; record the Experiment.
3. Run ingest with configuration B (only ONE knob changed).
4. Run the same set of test queries against each.
5. Compare results side-by-side in the Experiments view (max 2 at a time).

## Observability Contract

Every experiment records:
- `totalChunks`, `avgTokensPerChunk`, `totalTimeMs`
- Per-chunk `ChunkMetadata` (chunking time, embedding time, char range, section)
- For search experiments: `hybridAlpha`, `useBm25`, `useReranker`, `topKVector`,
  `topNRerank`, `parentContextLevels`, `autoTuneWeights`, `bestAlpha`, `rawQuery`

This metadata is the substrate for systematic comparison.
""",
}


@router.post("")
def seed(
    db: Neo4jClient = Depends(get_db),
) -> dict:
    created: int = 0
    skipped: List[str] = []
    created_ids: List[str] = []

    for filename, text in SAMPLE_DOCS.items():
        # Check if an upload-time placeholder Knowledge node already exists
        existing = db.get_document_text(filename)
        if existing:
            skipped.append(filename)
            continue
        knowledge = Knowledge(
            id=str(uuid.uuid4()),
            source_file=filename,
            total_tokens=max(1, len(text) // 4),
            embedding_method="Upload",  # marker — re-embedded at /ingest
            created_at=datetime.utcnow(),
            experiment_id="upload",  # pseudo experiment for seed docs
            vector=None,  # null vector → excluded from HNSW index
            text=text,
            chunk_index=0,
            char_start=0,
            char_end=len(text),
        )
        db.create_knowledge(knowledge)
        created += 1
        created_ids.append(knowledge.id)

    return {"created": created, "skipped": skipped, "createdIds": created_ids}
