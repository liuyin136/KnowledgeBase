# INC-003 — Rerank embed returned 512 rows for 5100-token prompt

## Status

closed

## Date

2026-07-11

## Symptom

Search fails at rerank phase: `query embed position N out of range for 512 embeddings`. Full prompt ~5100 tokens.

## Root cause

`JinaReranker` `n_batch` misaligned with `n_ctx`; llama.cpp returned only 512 hidden-state rows while marker position computed on full prompt.

## Fix

Align `n_batch=8192` with `n_ctx=8192` in `JinaReranker._ensure_embed_llm` (`backend/scripts/Jina/_jina_common.py`).

## Files touched

- `backend/scripts/Jina/_jina_common.py`
- `tests/test_rerank_tokens.py`

## Regression

```bash
docker compose exec -e IN_WORKER_EXEC=1 api-worker python -m pytest tests/test_rerank_tokens.py -q
```

## ADR

[ADR-004: Jina reranker n_batch / n_ctx alignment](../decisions/ADR-004-jina-rerank-n-batch-alignment.md). See [AGENTS.md](../../AGENTS.md) VRAM section for signal 6 vs rerank errors.
