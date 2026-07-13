# INC-005 — Phase 2.01 GLiNER2 + Qwen3 extraction build failures

## Status

closed

## Date

2026-07-13

## Scope

Phase 2.01 api-worker **model-downloader** stage: baking **GLiNER2** (`fastino/gliner2-base-v1`) and **Qwen3-8B** (`Qwen/Qwen3-8B`) into `/app/models`. Two independent build failures were hit during prep.

---

## Failure A — `snapshot_download` for library models

### Symptom

`docker compose build api-worker` downloaded GLiNER2 / LLM weights via `huggingface_hub.snapshot_download`. Build appeared to succeed, but runtime loaders failed — layout/tokenizer artifacts did not match `GLiNER2.from_pretrained(local)` or `transformers` causal LM loading.

### Root cause

**Raw HF repo snapshot ≠ library `save_pretrained` layout.**

| Model | Correct (build) | Wrong |
|-------|---------------|-------|
| GLiNER2 | `GLiNER2.from_pretrained(hub)` → `save_pretrained(/app/models/GLiNER2)` | `snapshot_download` |
| Qwen3-8B | `AutoTokenizer` + `AutoModelForCausalLM.from_pretrained(hub)` → `save_pretrained(/app/models/Qwen3-8B)` | `snapshot_download` |

### Fix

`backend/download_models2.py`: `download_gliner2_model()`, `download_qwen3_model()` use library-native hub load → local save only.

---

## Failure B — `gliner2[local]` with `--no-deps` in model-downloader (missing pydantic)

### Symptom

After switching to library download, model-downloader failed at GLiNER2 step:

```
Model ensure failed: No module named 'pydantic'
```

Liquid GGUF downloads had already succeeded; failure occurred when `GLiNER2.from_pretrained()` ran inside `download_models2.py`.

### Root cause

`docker/Dockerfile.worker` **model-downloader** stage installed:

```dockerfile
pip install "gliner2[local]" --no-deps --no-build-isolation
```

`--no-deps` skips **gliner2** transitive dependencies. **pydantic** (required by gliner2 at import/load time) was not installed in that stage.

**Note:** Runtime stage may still use `--no-deps` for `gliner2[local]` because `requirements-worker.txt` already pulls `pydantic` via `pydantic-settings`. **model-downloader is a minimal image** — it must not use `--no-deps` on gliner2 unless every required dependency is pinned explicitly in the same `pip install` line.

### Fix

`docker/Dockerfile.worker` model-downloader:

```dockerfile
pip install "huggingface_hub==1.22.0" "transformers>=4.48" "accelerate==1.6.0" \
    "sentencepiece==0.2.2" "gliner==0.2.24" "pydantic==2.13.4" \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
&& pip install "gliner2[local]" --no-build-isolation \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

- **Remove `--no-deps`** from model-downloader `gliner2[local]` install (allow pip to resolve gliner2 dependencies), **or** pin every transitive dep explicitly (pydantic at minimum).
- Explicit `pydantic==2.13.4` pin documents the failure and matches runtime `requirements-worker.txt`.

Verified: `docker compose build api-worker` completes model-downloader after this change.

---

## Runtime policy (unchanged)

- Load **only** from `/app/models/GLiNER2` and `/app/models/Qwen3-8B` — never hub ids at runtime.
- Qwen3: **4-bit bitsandbytes** via `scripts/Qwen/_qwen_common.py` → `app/services/extract_llm.py` for graph extraction chat.

## Files touched

- `backend/download_models2.py`
- `docker/Dockerfile.worker`
- `backend/scripts/gliner2/_gliner_common.py`
- `backend/scripts/Qwen/_qwen_common.py`
- `backend/app/services/extract_llm.py`
- `docs/decisions/ADR-005-extraction-model-gliner2-llama.md`
- `docs/pitfalls/TRAPS-PHASE-2.md`

## Regression

- Build: `docker compose build api-worker` (model-downloader prints GLiNER2 + Qwen3-8B ready paths)
- Smoke: `scripts/gliner2/gliner2-base-v1.py`, `scripts/Qwen/Qwen-8B.py`
- Unit: `tests/test_gliner_loader.py`, `tests/test_qwen_loader.py`, `tests/test_download_models2_extraction.py`, `tests/test_extract_llm.py`

## Wrong patterns

- `snapshot_download` for GLiNER2 or Qwen3-8B in this project
- `pip install gliner2[local] --no-deps` in **model-downloader** without pinning all transitive deps (pydantic, etc.)
- Assuming runtime-stage `--no-deps` discipline applies to the minimal model-downloader stage
