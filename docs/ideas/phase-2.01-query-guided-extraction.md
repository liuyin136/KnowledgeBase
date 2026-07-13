# Phase 2.01 — Query-Guided Extraction (GLiNER2 + Qwen3-8B)

## Problem Statement

How might we replace Phase 2.0 batch extraction with query-focused graph building so top-N chunks do not pollute the memory subgraph with irrelevant entities?

## Recommended Direction

Lock **2.01 BUILD** to **Query-Guided Extraction** with a two-model stack:

| Layer      | Choice                                                                                                                     |
| ---------- | -------------------------------------------------------------------------------------------------------------------------- |
| Focus      | `query_text` as extraction scope                                                                                           |
| NER        | GLiNER2 (`fastino/gliner2-base-v1`) @ `/app/models/GLiNER2`                                                               |
| LLM        | `Qwen/Qwen3-8B` @ `/app/models/Qwen3-8B` — **4-bit bitsandbytes** at runtime                                             |
| Prompt     | Query-guided system/user prompts                                                                                           |
| Call shape | **Batch** filtered chunks in one LLM call                                                                                  |
| Schema     | `entities[]` + `relationships[]` JSON                                                                                        |
| Downstream | 2.0 `merge_memory_graph`, community, episodic, LWW                                                                         |

**Supersedes:** Llama 3.1 + `HF_TOKEN`; per-chunk loop; `liquid-extract` GGUF default.

## Key Assumptions to Validate

- [x] GLiNER2 + Qwen3 smoke scripts pass (prep P2–P3)
- [x] Qwen3 4-bit stays under 7 GB VRAM on RTX 3070 Ti
- [ ] Name-based merge to `entity_id` without duplicate nodes

## MVP Scope

**In (prep slice)**

- `transformers`, `bitsandbytes`, `gliner2`
- `download_models2.py`: GLiNER2 + Qwen3 snapshots; no Llama
- Loaders: `_gliner_common.py`, `_qwen_common.py`, `qwen_runtime.py`
- Smoke: `scripts/gliner2/gliner2-base-v1.py`, `scripts/Qwen/Qwen-8B.py`, `scripts/Qwen/Qwen-8B-stress.py`
- ADR-005

**In (next slice)**

- `liquid_extract.py` wired to GLiNER2 + Qwen3
- CP-2.01-E2E G1–G4

## Canon Pointer

- Prep demos: [scripts/gliner2/](../../backend/scripts/gliner2/), [scripts/Qwen/](../../backend/scripts/Qwen/)
- Spec: [plan-phase-2.01.md](../../Download/RAG%20Workflow%20template/plan-phase-2.01.md)
- ADR: [ADR-005](../../docs/decisions/ADR-005-extraction-model-gliner2-llama.md)
