# ADR-005: Extraction model stack — GLiNER2 + Qwen3-8B

## Status

Accepted

## Date

2026-07-13

## Context

Phase 2.01 replaces Phase 2.0 batch `liquid_extract` (Liquid GGUF) with **query-guided extraction**:

| Layer | Role |
|-------|------|
| **GLiNER2** | Entity / NER pass over chunk text |
| **Qwen3-8B** | Instruct LLM for structured graph JSON (summary, entities, relations, claims) |

Six Liquid GGUF extraction variants were removed from the api-worker image. Prior Llama 3.1 + `HF_TOKEN` prep was abandoned in favor of open **Qwen/Qwen3-8B**.

Constraints: RTX 3070 Ti, ≤ 7 GB VRAM peak, single GPU slot (`WORKER_CONCURRENCY=1`).

## Decision

### Stack

| Component | Hub id | Local path | Runtime package |
|-----------|--------|------------|-----------------|
| NER | `fastino/gliner2-base-v1` | `/app/models/GLiNER2` | `gliner2[local]` |
| Extraction LLM | `Qwen/Qwen3-8B` | `/app/models/Qwen3-8B` | `transformers>=4.48` + `bitsandbytes==0.45.5` |

### Build-time (model-downloader stage)

1. **Library-native download only** — never `huggingface_hub.snapshot_download` for GLiNER2 or Qwen3 ([INC-005](../incidents/INC-005-snapshot-download-extraction-models.md)):
   - `GLiNER2.from_pretrained(hub)` → `save_pretrained(/app/models/GLiNER2)`
   - `AutoTokenizer` + `AutoModelForCausalLM.from_pretrained(hub)` → `save_pretrained(/app/models/Qwen3-8B)`
2. **Python 3.13** in model-downloader and runtime (`COPY --from=python:3.13-slim`) — see [INC-006](../incidents/INC-006-api-worker-py314-sentencepiece-build.md).
3. **pip order:** `torch==2.6.0` (cpu wheel in downloader; cu124 in runtime) before Tsinghua `requirements-worker.txt`.
4. **gliner2 in model-downloader:** `pip install "gliner2[local]"` **without `--no-deps`** (or pin all transitive deps including `pydantic`). Using `--no-deps` caused `No module named 'pydantic'` at GLiNER2 download ([INC-005](../incidents/INC-005-snapshot-download-extraction-models.md)).
5. No `HF_TOKEN` (Qwen3-8B is not gated).

### Runtime

1. Load **only** from `/app/models/GLiNER2` and `/app/models/Qwen3-8B` — never hub ids.
2. **GLiNER2:** `scripts/gliner2/_gliner_common.load_gliner2()` / `gliner_runtime.py`.
3. **Qwen3:** `load_qwen3_4bit()` with `BitsAndBytesConfig(load_in_4bit=True)` — `qwen_runtime.py` slot `qwen3-8b`.
4. **Extraction chat API:** `app/services/extract_llm.run_extract_chat((tokenizer, model), messages)` — used by `liquid_extract.py` and `graph_community.py` (replaces Liquid GGUF `run_chat`).
5. `liquid_runtime.load_extract_model()` delegates to `qwen_runtime` for backward compatibility with `tasks.extract_memory_graph`.
6. Worker startup: `ensure_model()` → `verify_all_models()` only (no Hub download at container start).
7. need to pip install perf and latest bitsandbytes.

### Image contents removed / retained

- **Removed:** six deprecated Liquid extract GGUF keys; Llama weights; legacy `jica98/qwen3.5-4B-super-coder` GGUF; Jina tasks other than retrieval + reranker.
- **Retained:** `liquid-350m`, `liquid-8b` (blueprint scripts); Jina retrieval GGUF + reranker GGUF/projector (search path, not extraction).

## Alternatives considered

| Option | Verdict |
|--------|---------|
| Meta-Llama-3.1-8B-Instruct | Rejected — gated (`HF_TOKEN`); VRAM without quantization |
| Keep Liquid-extract GGUF | Rejected — bloat; weak structured JSON |
| Full-precision Qwen3-8B | Rejected — ~16 GB VRAM |
| `snapshot_download` for weights | Rejected — [INC-005](../incidents/INC-005-snapshot-download-extraction-models.md) |
| `gliner2[local] --no-deps` in model-downloader | Rejected — missing pydantic — [INC-005](../incidents/INC-005-snapshot-download-extraction-models.md) |

## Consequences

- Build downloads ~16 GB Qwen3 weights + GLiNER2; first build is long but needs no token.
- 4-bit Qwen3 fits RTX 3070 Ti VRAM budget on smoke tests.
- Runtime stage may keep `gliner2[local] --no-deps` because `requirements-worker.txt` already installs shared deps.
- Regression: `tests/test_gliner_loader.py`, `tests/test_qwen_loader.py`, `tests/test_extract_llm.py`, `tests/test_memory_vram.py`.
- Rebuild: `docker compose build api-worker`.

## Wrong patterns

- `snapshot_download` for GLiNER2 or Qwen3
- Hub ids at runtime (`fastino/gliner2-base-v1`, `Qwen/Qwen3-8B`)
- `gliner2[local] --no-deps` in **model-downloader** without explicit transitive pins
- Qwen3 full-precision on 8 GB GPU
- `HF_TOKEN` for Phase 2.01 extraction prep
- Liquid `_liquid_common.run_chat` for new extraction paths (use `extract_llm.run_extract_chat`)
