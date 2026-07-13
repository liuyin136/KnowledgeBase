# TRAPS — Phase 2 (graph memory)

Grep before BUILD steps for Phase 2 ([plan-phase-2.md](../../Download/RAG%20Workflow%20template/plan-phase-2.md)).

**Prereq trap (from spec):** search hits for memory links must use v1.62 `Knowledgechunk_grand` ids — not legacy flat `KnowledgeChunk` only. See [HybridSearchAndFusionEngine_v1.51.md](../../Download/RAG%20Workflow%20template/HybridSearchAndFusionEngine_v1.51.md) Phase 2 row.

**2026-07-12:** Liquid YAML output with unquoted colons in claim text (e.g. `(.cursor/rules/docker-build.mdc):`) crashes `parse_graph_yaml` on re-extract — use JSON-first prompt + `json.loads` before YAML fallback.

**2026-07-12:** Large JSON graph output truncated at `max_tokens=1024` — job fails before LWW merge; looks like version/LWW bug but is parse failure. Raise tokens (2048), shorten chunk text, compact-prompt retry.

**2026-07-13:** Phase 2.01 prep — do **not** download GLiNER2 or Qwen3 via `huggingface_hub.snapshot_download`. **Do instead:** build-time library `from_pretrained` → `save_pretrained` to `/app/models/GLiNER2` and `/app/models/Qwen3-8B`; runtime Qwen3 loads with **4-bit bitsandbytes** from local path only. See [ADR-005](../decisions/ADR-005-extraction-model-gliner2-llama.md), [INC-005](../incidents/INC-005-snapshot-download-extraction-models.md).

**2026-07-13:** model-downloader — do **not** `pip install gliner2[local] --no-deps` unless every transitive dep (at minimum **pydantic**) is pinned in the same stage. Failure: `No module named 'pydantic'` during `GLiNER2.from_pretrained` in `download_models2.py`. Runtime stage may keep `--no-deps` when `requirements-worker.txt` already supplies deps. See [INC-005](../incidents/INC-005-snapshot-download-extraction-models.md).

**2026-07-13:** `api-worker` runtime stage — do **not** use Ubuntu 26.04 system Python 3.14 for `pip install` (`sentencepiece`, `torch` have no cp314 wheels → source build fails exit 127). **Do instead:** `COPY --from=python:3.13-slim /usr/local /usr/local`; install `torch==2.6.0` from `download.pytorch.org/whl/cu124` **before** Tsinghua `requirements-worker.txt`; pin `sentencepiece==0.2.2` not `0.2.0` (no cp313 wheel). See [INC-006](../incidents/INC-006-api-worker-py314-sentencepiece-build.md).

---

<!-- Append new entries above this line (newest first). -->
