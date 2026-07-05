# Ingest LongText Fix - v1.33

**Date**: 2026-07-05  
**Status**: Fixed  
**Related**: LongText ingestion, Jina v5 embedding, ChildChunk workflow

## Problem
LongText ingest (and related ChildChunk parent embedding) was failing with:

```
LongText ingest failed: Embedding failed (jina-embeddings-v5-text-small): 
SentenceTransformer.encode() has been called with additional keyword arguments 
that this model does not use: ['texts']. 
As per SentenceTransformer.get_model_kwargs(), the valid additional keyword arguments are: ['task', 'truncate_dim'].
```

## Root Cause
In `backend/app/services/embedding.py`, the `embed_batch()` method was calling:

```python
self._model.encode(
    batch,
    texts=batch,                    # unsupported
    ...
    task="retrieval",
    prompt_name="document"          # unsupported
)
```

The Jina Embeddings v5 small model (loaded via `SentenceTransformer(..., trust_remote_code=True)`) only accepts `task` and `truncate_dim` as additional kwargs. `texts=` and `prompt_name=` are not recognized by this model's encode implementation.

This affected:
- LongText full-document / sliding-window embeddings
- ChildChunk parent (full text as LongText) + children

## Changes Made

### 1. Fixed encode call (`backend/app/services/embedding.py`)
- Removed unsupported `texts=` and `prompt_name=` kwargs.
- Now uses the supported form:
  ```python
  emb = self._model.encode(
      batch,                    # list of text(s) as positional argument
      batch_size=...,
      convert_to_numpy=False,
      convert_to_tensor=True,
      normalize_embeddings=True,
      show_progress_bar=False,
      task="retrieval",
  )
  ```
- Updated module docstring, method docstrings, and inline comments to reflect correct usage.
- Clarified that `task="retrieval"` is used for document/passage embeddings during ingestion.

### 2. Explicit GPU device handling
- Added in `load()`:
  ```python
  explicit_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
  self._model = self._model.to(explicit_device)
  self._device = str(explicit_device)
  ```
- Ensures model runs on GPU when available (cuda) or falls back to CPU.
- Combined with existing `SentenceTransformer(..., device=device)`.

### 3. Documentation & comment cleanup
- Updated comments in:
  - `backend/app/services/orchestrator.py` (ingest_long_text, ingest_child_chunk)
  - `backend/app/core/config.py`
  - `backend/app/core/constants.py`
- Removed references to unsupported `prompt_name`.
- Confirmed architecture: `SentenceTransformer.encode()` (with `task="retrieval"`) is used uniformly for **both** LongText (full text or windows) and ChildChunk paths. No separate raw `transformer` path is needed or used for LongText.

### 4. Config alignment (user update)
- `config.py` updated to treat Jina v5 small as 1024-dim native (consistent with `truncate_dim=1024` and pre-set Neo4j 1024-dim vector indexes).
- All ingestion vectors (LongText + ChildChunk) are 1024-dimensional.

## Architecture Notes
- **LongText embedding**: The full document (or large windows) is passed as a single passage (`[full_text]`) to `encode(..., task="retrieval")`. This produces the context vector stored on `:Knowledge` nodes (embedding_method="LongText").
- **ChildChunk**: Same encode path is used for the parent (full doc) and every child chunk. Children are stored as `:KnowledgeChunk` with `embedding_method="ChildChunk"` and linked via `[:HAS_CHUNK]`.
- sentence-transformers is the correct abstraction for both cases. It handles tokenization + transformer forward pass for single long texts or batches of chunks.
- Passing a list positionally (`batch`) is the proper way to "wrap" one or more texts.

## Result
- LongText ingestion now succeeds.
- ChildChunk (all 3 methods: Recursive, Semantic, Structure-Aware) unaffected and continue to work.
- GPU usage explicitly ensured.
- Code and docs aligned with actual supported Jina v5 + SentenceTransformer API.

## Files Changed
- `backend/app/services/embedding.py` (core fix + GPU + docs)
- `backend/app/services/orchestrator.py` (comments)
- `backend/app/core/config.py` (user's 1024 update + docs)
- `backend/app/core/constants.py` (docs)
- `upload/ingest-long-text_v1.33.md` (this summary)