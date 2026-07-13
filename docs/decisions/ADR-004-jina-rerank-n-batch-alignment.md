# ADR-004: Jina reranker n_batch / n_ctx alignment

## Status

Accepted

## Date

2026-07-12

## Context

Hybrid search fails at the rerank phase with:

```
query embed position N out of range for 512 embeddings
```

when the rerank prompt is ~5100 tokens. This is **not** a Matryoshka embedding dimension mismatch (256/512/1024). The reranker computes marker token positions on the **full** prompt, but `llama.cpp` returned only **512** rows of per-token hidden states.

Source incident: [INC-003](../incidents/INC-003-rerank-n-batch-512.md).

## Decision

`JinaReranker._ensure_embed_llm` must keep **`n_batch` aligned with `n_ctx`** for the embed (hidden-state) pass — both **8192** for production rerank (see `backend/scripts/Jina/_jina_common.py`).

Do not assume `len(embeddings)` equals full prompt token count when diagnosing rerank failures.

## Alternatives considered

### Truncate prompt only

Rejected: marker positions would still be wrong relative to truncated embed output without matching batch/context sizing.

### Lower n_ctx to 512

Rejected: loses long-context rerank capability; does not fix misalignment root cause.

## Consequences

- Regression: `tests/test_rerank_tokens.py`
- Distinguish rerank position errors from VRAM signal 6 (`ggml_cuda_error`) — see [AGENTS.md](../../AGENTS.md) VRAM section
- New DEBUG incidents with `adr_candidate: true` may auto-draft ADR via stop hook

## Wrong patterns

- Diagnosing rerank `embed position out of range` as coarse vector / Matryoshka dim mismatch
- Setting `n_ctx=8192` without matching `n_batch` on reranker embed LLM
- Assuming 512 embed rows means the query was only 512 tokens (often batch cap, not prompt length)
