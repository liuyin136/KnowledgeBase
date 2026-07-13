# INC-006 — api-worker build fails: sentencepiece on Python 3.14

## Status

closed

## Date

2026-07-13

## Symptom

`docker compose build api-worker` fails at runtime stage:

```
ERROR: Failed building wheel for sentencepiece
Command '['./build_bundled.sh', '0.2.0']' returned non-zero exit status 127
```

## Root cause

`nvidia/cuda:13.3.0-runtime-ubuntu26.04` ships **Python 3.14** (no cp314 wheels). **`sentencepiece==0.2.0`** has no cp313 wheel either — pip builds from source and fails (`cmake: not found`, exit 127).

Secondary: runtime `pip install -r requirements-worker.txt` from Tsinghua only skipped ADR-005 torch cu124-first install.

## Fix

`docker/Dockerfile.worker` runtime stage:

1. `COPY --from=python:3.13-slim /usr/local /usr/local` — use Python 3.13 with prebuilt wheels
2. `pip install torch==2.6.0` from `download.pytorch.org/whl/cu124` before `requirements-worker.txt`
3. Pin `sentencepiece==0.2.2` (cp313 wheel; `0.2.0` forces source build)
4. Extraction LLM is **Qwen/Qwen3-8B** (open) — no `HF_TOKEN` at build time (supersedes gated Llama prep)

## Files touched

- `docker/Dockerfile.worker`
- `backend/requirements-worker.txt`
- `docs/pitfalls/TRAPS-PHASE-2.md`

## Regression

`docker compose build api-worker` completes runtime pip layer (no `HF_TOKEN`).

## Wrong patterns

- Using Ubuntu 26.04 default `python3` (3.14) for worker ML deps
- Installing `torch` only from Tsinghua after Phase 2.01 extraction deps
