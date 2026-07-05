# Task 5 — v1.3 Embedding & Reranker Model Migration (Jina v5 default + BGE-M3 toggle)

Agent: full-stack-developer (v1.3 embedding migration)
Task: Migrate the Local-First RAG Experimentation Platform v1.3 backend (FastAPI, Python 3.12) from BGE-M3-only to **Jina v5 as default + BGE-M3 as toggleable alternative**, AND add a frontend Settings toggle (read-only display + switch instructions).

## Work Log

- Read `worklog.md` (Tasks 1, 2, 5-a/b/c, 6, 7, 9+10) to load full project context — v1.2 pivot to FastAPI+Neo4j is complete; v1.3 now migrates models. Confirmed construction note #1 (float32 cast) was already in place on the BGE-M3 path and must be preserved on EVERY encode path for BOTH models.
- Read all target files before editing:
  - `backend/app/services/embedding.py` — BGE-M3 via sentence-transformers; construction note #1 float32 cast (`emb.detach().cpu().to(torch.float32)`).
  - `backend/app/services/retrieval.py` — CrossEncoder reranker (lines ~339-393), `_ensure_reranker` + `_rerank` use `settings.bge_reranker_repo` + `max_length=512`.
  - `backend/app/core/config.py` — Pydantic Settings with `bge_m3_repo`, `bge_reranker_repo`, `embedding_model_name`, `reranker_model_name`, `embedding_dim`.
  - `backend/app/core/constants.py` — `EMBEDDING_MODEL="BAAI/bge-m3"`, `EMBEDDING_DIM=1024`, `RERANKER_MODEL="BAAI/bge-reranker-base"`.
  - `backend/scripts/download_models.py` — downloads BGE-M3 + BGE-reranker-base.
  - `backend/requirements.txt` — pinned `sentence-transformers==3.3.1`, `transformers==4.46.3`.
  - `docker/Dockerfile.backend` — model-download stage (NOT modified — main agent owns it).
  - `docker/docker-compose.yml` — `EMBEDDING_MODEL: BAAI/bge-m3` env var on backend + api-worker.
  - `src/lib/rag/types.ts`, `src/lib/rag/constants.ts` (`EMBEDDING_MODEL="z-ai-embedding-v1"`, `EMBEDDING_DIM=1024`, `RERANKER_MODEL="z-ai-llm-reranker"`).
  - `src/store/use-ui-store.ts` — ViewKey type (5 entries).
  - `src/components/rag/views/dashboard-view.tsx` — System Connections cards (842 lines, observed pattern).
  - `src/lib/api-client.ts` — api methods.
  - `src/app/api/v1/dashboard/route.ts` — Next.js proxy with hardcoded BGE-M3 string.
  - `src/components/rag/sidebar.tsx`, `src/components/rag/shared/view-header.tsx`, `src/components/rag/shared/backend-offline.tsx`.

### Backend changes

- **`backend/app/core/config.py`** — rewrote Settings:
  - Added `embedding_model: str = "jina-v5-small"` (selectable: "jina-v5-small" | "bge-m3") + `reranker_model: str = "jina-v3"` (selectable: "jina-v3" | "bge-reranker-base").
  - Added `jina_v5_repo = "jinaai/jina-embeddings-v5-text-small"`, `jina_reranker_repo = "jinaai/jina-reranker-v3"`. Kept `bge_m3_repo` + `bge_reranker_repo`.
  - Module-level lookup tables `EMBEDDING_MODEL_IDS`, `RERANKER_MODEL_IDS`, `MODEL_NATIVE_DIM`.
  - Added derived properties: `embedding_repo` (active HF repo from logical id), `reranker_repo`, `embedding_model_name` (local subdir name), `reranker_model_name`, `model_dim` (Jina v5 small = 1536, BGE-M3 = 1024), `reranker_max_length` (Jina v3 = 8192, BGE-reranker-base = 512).
  - `embedding_dim` STAYS at 1024 (Neo4j vector indexes are 1024-dim cosine — Jina uses Matryoshka truncation to 1024, BGE-M3 is natively 1024; BOTH write into the SAME indexes).
  - Added Pydantic validators: `_embedding_model_must_be_known` + `_reranker_model_must_be_known` reject unknown logical ids at startup.

- **`backend/app/core/constants.py`** — replaced the BGE-only constants block with v1.3 Jina-default + BGE-toggle constants:
  - `EMBEDDING_MODEL = "jinaai/jina-embeddings-v5-text-small"` (active repo id, v1.3 default), `EMBEDDING_MODEL_LOGICAL = "jina-v5-small"`.
  - `EMBEDDING_DIM = 1024` (unchanged — STABLE for both models).
  - `RERANKER_MODEL = "jinaai/jina-reranker-v3"`, `RERANKER_MODEL_LOGICAL = "jina-v3"`.
  - Kept `BGE_M3_REPO` + `BGE_RERANKER_REPO` as reference constants.
  - Added `JINA_TASK_QUERY = "retrieval.query"`, `JINA_TASK_PASSAGE = "retrieval.passages"`.
  - Added `JINA_V5_SMALL_NATIVE_DIM = 1536`, `BGE_M3_NATIVE_DIM = 1024`.

- **`backend/app/services/embedding.py`** — full refactor of `EmbeddingModule`:
  - `__init__` captures `self._model_id = settings.embedding_model` (logical id) for observability.
  - `load()` resolves the model + loading kwargs conditionally:
    - Jina v5 small: `SentenceTransformer(model_src, device=device, trust_remote_code=True, truncate_dim=settings.embedding_dim)` — `truncate_dim=1024` is the sentence-transformers knob for the Matryoshka `dimensions=` parameter. `trust_remote_code=True` is required because Jina v5 ships a custom modeling file.
    - BGE-M3: `SentenceTransformer(model_src, device=device)` — vanilla, no task/dimensions kwargs.
  - `embed_batch(texts, *, batch_size=None, is_query=False)` — accepts `is_query`. For Jina, sets `encode_kwargs["task"] = "retrieval.query" if is_query else "retrieval.passages"`. For BGE-M3, no task kwarg (flag is ignored). Matryoshka truncation is configured at LOAD time via `truncate_dim` (not at encode time — `truncate_dim` is the supported sentence-transformers knob).
  - **Construction note #1 (MANDATORY) preserved for BOTH models**: `emb.detach().cpu().to(torch.float32)` cast on every encode path with explicit comment explaining numpy cannot handle bfloat16 and Jina on GPU may also output bfloat16.
  - `embed(text, *, is_query=False)`, `embed_with_retry(text, *, experiment_id=None, is_query=False)`, `embed_batch_with_retry(texts, *, experiment_id=None, is_query=False)` all thread `is_query` through. Retry logic unchanged (max 3 attempts, exp backoff 1s/2s/4s, halve batch on OOM).
  - Added `model_id` property for observability.

- **`backend/app/services/retrieval.py`** — refactored `_ensure_reranker`:
  - Uses `settings.reranker_repo` (resolves to Jina v3 or BGE-reranker-base based on `reranker_model`).
  - `max_length=settings.reranker_max_length` (8192 for Jina v3, 512 for BGE-reranker-base).
  - `trust_remote_code=True` only for Jina v3 (BGE-reranker-base is a vanilla transformer).
  - `_rerank` unchanged — `CrossEncoder.predict()` API is identical for both. Float32 cast preserved.

- **`backend/app/services/orchestrator.py`** — updated all 4 embed call sites:
  - `ingest_long_text` per-window: `embed_with_retry(b.text, experiment_id=experiment_id, is_query=False)` (documents → Jina task="retrieval.passages"; BGE-M3 ignores flag).
  - `ingest_child_chunk` parent LongText: `embed_with_retry(text, experiment_id=experiment_id, is_query=False)` (parent doc is a PASSAGE).
  - `ingest_child_chunk` per-child: `embed_with_retry(b.text, experiment_id=experiment_id, is_query=False)`.
  - `run_search` query: `embed_with_retry(raw_query, experiment_id=experiment_id, is_query=True)` (queries → Jina task="retrieval.query"; BGE-M3 ignores flag).

- **`backend/app/api/v1/dashboard.py`** — `system` block now reports:
  - `embeddingModel` (active repo id), `embeddingModelLogical` (logical id), `embeddingDim` (1024 — actual dim written to Neo4j), `embeddingNativeDim` (model's native dim, e.g. 1536 for Jina v5 small).
  - `rerankerModel` (active repo id), `rerankerModelLogical`, `rerankerMaxLength`.
  - Stack string updated to "v1.3 — Jina v5 default + BGE-M3 toggle".

- **`backend/scripts/download_models.py`** — v1.3 default = Jina v5 small + Jina Reranker v3. Optional `DOWNLOAD_BGE=1` env var downloads BGE-M3 + BGE-reranker-base in the same run so the toggle works without re-downloading at runtime. Existing `DOWNLOAD_RERANKER=0` flag still respected (skips default reranker).

- **`backend/requirements.txt`** — added `einops==0.8.0` (some Jina model implementations need it; loading Jina v5 may fail without it). Other pins unchanged (`sentence-transformers==3.3.1`, `transformers==4.46.3` — already support Jina v5).

### Frontend changes

- **`src/lib/rag/constants.ts`** — replaced stale v1 sandbox placeholders:
  - `EMBEDDING_MODEL = "jinaai/jina-embeddings-v5-text-small"`, `EMBEDDING_MODEL_LOGICAL = "jina-v5-small"`.
  - `EMBEDDING_DIM = 1024` (unchanged).
  - `JINA_V5_SMALL_NATIVE_DIM = 1536`, `BGE_M3_NATIVE_DIM = 1024`.
  - `RERANKER_MODEL = "jinaai/jina-reranker-v3"`, `RERANKER_MODEL_LOGICAL = "jina-v3"`.
  - Kept `BGE_M3_REPO`, `BGE_RERANKER_REPO` as reference constants.
  - Added `JINA_TASK_QUERY`, `JINA_TASK_PASSAGE` for the Settings UI info card.

- **`src/store/use-ui-store.ts`** — extended `ViewKey` with `"settings"`.

- **`src/components/rag/sidebar.tsx`** — added 6th nav item "Settings" with `Settings` (gear) icon + description "Active models & how to switch". Footer text updated to "v1.3 · Jina v5 default + BGE-M3 toggle".

- **`src/components/rag/views/settings-view.tsx`** (NEW, ~580 lines) — read-only model display + switch instructions:
  - Pulls the active model from the dashboard `system` field via TanStack Query (`api.dashboard`).
  - **Backend offline banner**: shared `<BackendOffline>` component when `health.backend.status === "offline"`.
  - **v1.3 decision card**: explains why the UI is read-only (env-var driven, runtime model reload is risky with GPU memory + vectors are model-specific). Two info boxes: "Why read-only?" + "Indexes stay 1024-dim".
  - **Active Models** section: 2 cards showing the currently loaded embedding + reranker (repo id, logical id, dim, native dim, max length).
  - **Embedding Model Options** section: 2 cards (Jina v5 small + BGE-M3) with highlights, descriptions, native dim, "active" badge. Jina card has "Matryoshka" badge; BGE card notes "v1.2 fallback".
  - **Reranker Model Options** section: 2 cards (Jina Reranker v3 + BGE Reranker base) with max length + "active" badge.
  - **How to Switch** section: 4-step ordered list (edit .env → recreate containers → re-ingest → verify via Dashboard). Includes copy-paste snippets for `docker/.env` + `docker compose up -d --force-recreate backend api-worker`. Step 3 has an amber alert reminding that vectors are model-specific (re-ingest required) but the Neo4j vector indexes themselves stay 1024-dim.
  - **Pre-downloading BGE** section: explains `docker compose run --rm backend env DOWNLOAD_BGE=1 python scripts/download_models.py` so the toggle is instant.
  - **v1.3 architecture notes** card: bullet list documenting construction note #1 (float32 cast preserved for both), Jina task conditioning, Matryoshka truncation, reranker max_length differences, switching models ≠ switching indexes.

- **`src/app/page.tsx`** — imports + renders `<SettingsView />` for `view === "settings"`. Footer text updated to "RAG Lab v1.3 · Local-First · Embedding: Jina v5 small (default) · BGE-M3 toggle · Jina task-conditioned + Matryoshka 1024".

- **`src/app/api/v1/dashboard/route.ts`** — when backend is online, forwards its `system` block verbatim (which now contains `embeddingModel`, `embeddingModelLogical`, `embeddingNativeDim`, `rerankerModel`, `rerankerModelLogical`, `rerankerMaxLength`). When backend is offline, falls back to a v1.3 default system block (Jina v5 small + Jina Reranker v3) so the UI still renders with the correct default displayed.

### Docker changes

- **`docker/docker-compose.yml`** — updated both `backend` and `api-worker` services:
  - `EMBEDDING_MODEL: jina-v5-small` (was `BAAI/bge-m3`).
  - Added `RERANKER_MODEL: jina-v3`.
  - Added inline comment explaining the v1.3 toggle workflow (set `EMBEDDING_MODEL=bge-m3` + `RERANKER_MODEL=bge-reranker-base`, recreate containers, re-ingest).
  - `EMBEDDING_DIM: "1024"` unchanged — STABLE for both models.

- **`docker/Dockerfile.backend`** — NOT modified (main agent is rewriting it). The download_models.py script changes are sufficient to make the toggle work once the Dockerfile is regenerated; the existing inline download script in the Dockerfile will be updated by the main agent to match.

## Stage Summary

- **Default models changed**: embedding is now Jina v5 small (`jinaai/jina-embeddings-v5-text-small`), reranker is now Jina Reranker v3 (`jinaai/jina-reranker-v3`). BGE-M3 + BGE-reranker-base remain available as toggleable alternatives via `EMBEDDING_MODEL` / `RERANKER_MODEL` env vars.
- **Construction note #1 (float32 cast) PRESERVED on ALL encode paths for BOTH models**. The `emb.detach().cpu().to(torch.float32)` cast is in `embed_batch` with explicit comment explaining Jina on GPU may also output bfloat16.
- **`task="retrieval"` implemented for Jina** (query vs passages): orchestrator passes `is_query=True` for queries (`task="retrieval.query"`) and `is_query=False` for documents/passages (`task="retrieval.passages"`). BGE-M3 ignores the flag.
- **Matryoshka truncation to 1024 for Jina**: `SentenceTransformer(..., truncate_dim=settings.embedding_dim)` at load time so Jina produces 1024-dim vectors into the SAME Neo4j indexes (no re-indexing required when switching models).
- **Frontend Settings view delivered**: 6th sidebar item "Settings" with gear icon → read-only model display (Active Models + Embedding Options + Reranker Options) + 4-step "How to Switch" instructions + "Pre-downloading BGE" + v1.3 architecture notes. BackendOffline banner shown when FastAPI is unreachable.
- **Decision documented**: model selection is env-var driven at container start; Settings UI is READ-ONLY (no runtime model reload — too risky with GPU memory + vectors are model-specific).
- **`einops==0.8.0`** added to requirements.txt for Jina model compatibility.
- **Verifications all green**:
  - `python3 -m compileall backend/app backend/scripts` → exit 0.
  - `bunx tsc --noEmit` (excluding examples/skills) → 0 errors in src/.
  - `bun run lint` → exit 0.
- **Files modified (15)**:
  - `backend/app/core/config.py` (rewrote Settings with v1.3 model selection + derived properties).
  - `backend/app/core/constants.py` (Jina-default constants + task strings + native dims).
  - `backend/app/services/embedding.py` (conditional Jina v5 vs BGE-M3 + is_query + Matryoshka + float32 cast preserved).
  - `backend/app/services/retrieval.py` (conditional Jina v3 vs BGE-reranker + max_length).
  - `backend/app/services/orchestrator.py` (is_query on all 4 embed call sites).
  - `backend/app/api/v1/dashboard.py` (system block reports active model details).
  - `backend/scripts/download_models.py` (Jina default + optional BGE via DOWNLOAD_BGE=1).
  - `backend/requirements.txt` (added einops==0.8.0).
  - `src/lib/rag/constants.ts` (v1.3 Jina-default constants).
  - `src/store/use-ui-store.ts` (added "settings" to ViewKey).
  - `src/components/rag/sidebar.tsx` (added Settings nav item + v1.3 footer).
  - `src/components/rag/views/settings-view.tsx` (NEW — read-only model display + switch instructions).
  - `src/app/page.tsx` (renders SettingsView + v1.3 footer).
  - `src/app/api/v1/dashboard/route.ts` (forwards backend system block verbatim + v1.3 fallback).
  - `docker/docker-compose.yml` (EMBEDDING_MODEL=jina-v5-small + RERANKER_MODEL=jina-v3 on backend + api-worker).
