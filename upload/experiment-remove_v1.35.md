# Experiment Node + experiment_id Removal & Full Documents Redesign (v1.35)

**Date:** 2026-07-05  
**Workspace:** D:\KnowledgeBase2 (branch: v1.3-replace)  
**Trigger:** `/code-review-and-quality , 全個repo review一次, 根據docker-compose build的error log, 一直iterate to built successful to all success.`  
**Outcome:** All services (backend, api-worker, frontend) build successfully after full cleanup. "Experiments" concept and :Experiment node completely removed; functionality repurposed to Documents (source_file-based :Knowledge / :KnowledgeChunk).

## Session Goal (from first principles + user directives)
- Delete the entire :Experiment node layer and every `experiment_id` property from the data model.
- Remove experiments API endpoints, routes, views, and related code.
- Repurpose the UI/flows named "Experiments" → "Documents". Documents page must use the only working Cypher path (Ingest documents list grouped by source_file + head(collect) for :Knowledge).
- Uploaded files = :Knowledge (embedding_method="Upload"), ingested = additional :Knowledge ("LongText") + :KnowledgeChunk children.
- Keep **minimal** internal run/job correlation ids (still called experiment_id in some places) for ProgressTracker, logs, jobs, observability — but **no** :Experiment nodes or DB fields.
- Full repo review + iterate fixes from actual `docker compose build` (and direct equivalent) error logs until **zero failures** across all images.
- Follow ponytail: minimal diff, delete over keep, no new abstractions, reuse existing (documents list Cypher), clean only what blocks build or is dead.

## Key Redesign Decisions
- :Experiment node + all experiment_id on Knowledge/KnowledgeChunk/UserQuery/Memory → deleted.
- No more `create_experiment`, `list_experiments`, `get_experiment`, `list_chunks_for_experiment`, `recent_experiments`.
- Documents list uses `list_documents` (source_file group by) + `list_chunks_for_source_file`.
- Dashboard: experiments stats hard 0 + empty recentExperiments.
- Search / ingest history now document-scoped (or stubbed empty).
- Frontend: experiments-view.tsx → documents-view.tsx (repurposed); activeExperimentId → activeDocumentId; api.experiments.* → api.documents.* .
- Internal "experimentId" (uuid) retained in job responses, progress, logging, and a few metadata shapes (for run tagging).

## Build Error Iteration Log (docker-compose + direct)
Initial state after prior renames had many breakage points.

1. **TS parse errors (ecmascript source failed in next build inside docker/frontend)**:
   - search-view.tsx:666 — stray lone `,` after config in mutate object (`config, ,`).
   - documents-view.tsx:1059 — broken ternary/?? expressions + type casts after mass rename (e.g. `e.id !== experimentId`, `??` on non-nullable).
   - Fix: remove stray commas; rewrite expressions cleanly (e.g. `e.description ? ...slice(0,60) : ''`); update types.

2. **Import / module errors**:
   - Deleted experiments.py but some imports or pyc references remained.
   - dashboard, router, api-client still pulling old experiments paths.
   - Fix: excise all imports, stub history to `Paginated(items=[], total=0...)`, update router includes.

3. **Cypher / neo4j_client breakage**:
   - "Variable `k` not defined" in list_documents (WITH scoping).
   - list_chunks_for_experiment still referenced.
   - Fix: rewrite using source_file only; delete old methods; dashboard_stats returns experiments: {0,0,0}.

4. **Docker / compose layer issues**:
   - Dockerfile comments still said "Experimentation Platform".
   - Frontend build inside alpine used `bun run build || npx next build`.
   - Repeated full compose runs (some killed for timeout), switched to targeted `npx next build`, `docker build -f ...`, `docker compose build frontend` / `backend`.
   - Final runs: all CACHED or fresh layers succeed → images: knowledgebase2-backend, api-worker (same image), frontend.

5. **Post-clean alias & dead-param drift (this review pass)**:
   - search-view still passed `experimentId` to `api.search.start` and `api.memories.list` (ignored by backend).
   - Destructuring aliases `activeDocumentId: activeExperimentId`.
   - Fix: stripped dead params from types + calls; switched to direct `activeDocumentId` / `setActiveDocument`.

Verification commands run repeatedly:
- `npx next build` → "Compiled successfully" + pages generated (multiple times, including after edits).
- Python: `py_compile` on all backend/app/*.py → 0 errors.
- `docker compose config` → OK.
- `docker compose build` (and per-service) → images built / CACHED + "DONE", no FATAL.
- Existing images confirmed (backend ~24 GB with CUDA, frontend ~311 MB).

## Summary of Changes (from git diff --stat + session edits)

### Deletions (major cleanup)
- `backend/app/api/v1/experiments.py`
- `src/app/api/v1/experiments/*` (route.ts + [id]/*)
- `src/components/rag/views/experiments-view.tsx` (1522 lines)
- `backend/app/api/v1/seed.py` (and frontend seed route)
- `backend/app/db/neo4j_client copy.py` (stray)
- Old experiment methods across neo4j_client, orchestrator, etc.

### Backend Core
- `backend/app/db/neo4j_client.py` (hundreds of lines): Cypher + methods switched to source_file / documents; stubs removed; dashboard experiments=0.
- `backend/app/models/neo4j_models.py`: experiment_id stripped from models; Experiment class deleted.
- `backend/app/services/orchestrator.py`: removed experiment creation + id passing in Knowledge/KnowledgeChunk/UserQuery/Memory.
- `backend/app/api/v1/{documents,ingest,search,memory,dashboard,router}.py`: experiment_id removed from paths/params/returns; history/recent stubbed.
- `backend/app/schemas/ingest.py`, `document.py`: adjusted; `experiment.py` schema kept only for IngestConfig + internal RunMetadata.
- `core/constants.py`, `logging.py`, `exceptions.py`, `config.py`: minor (enums + correlation kept; titles/docs updated).

### Frontend
- New/repurposed: `src/components/rag/views/documents-view.tsx` (list/detail/compare now on documents + source_file chunks).
- `src/lib/api-client.ts`: experiments block removed; documents.* added; search/ingest signatures cleaned.
- `src/store/use-ui-store.ts`: ViewKey "documents"; active* → activeDocumentId.
- `src/components/rag/views/{search,ingest,dashboard,memory,settings}-view.tsx`, `sidebar.tsx`, `page.tsx`: updated to documents, removed experiment UI, cleaned aliases + dead params.
- `src/lib/rag/{types,metadata,errors}.ts`: Experiment* types retained for metadata/run shapes only.
- API proxy routes under documents expanded ([id]/chunks, [id]/text).

### Docker / Infra / Docs
- `docker-compose.yml`, `docker/docker-compose.yml`, `Dockerfile.backend`, `Dockerfile.frontend`: comments updated ("experiment node deleted", "Documents focus").
- `upload/neo4j-schema-v1.1.md`: redesign notes + :Experiment section removed.
- Various README.md, agent-ctx (historical), log txts (untouched as artifacts).

### This-session minimal clean (ponytail)
- Removed leftover `experimentId` from search mutation types/calls and memories.list (search-view + api-client).
- Direct `activeDocumentId` / `setActiveDocument` (no more alias destructuring) in documents-view + search-view.

## Code Review (per code-review-and-quality axes)
- **Correctness**: Documents list now drives from the working source_file Cypher. Job/run ids still flow for ingest/search progress (verified by response shapes). No :Experiment CREATE/MATCH left in active paths.
- **Readability & Simplicity**: Stray syntax from rename fixed. Aliases reduced in final pass. Dead experiment API code deleted (big win).
- **Architecture**: Full layer removal (YAGNI). schemas/experiment.py + internal ids retained because they are still used by orchestrator/metadata/jobs — no pointless rename.
- **Security / Perf**: No impact. No new surfaces. Pagination and list queries unchanged in spirit.
- **Verification story**: Direct builds + docker compose logs captured repeatedly. All ended in success. No "I'll fix later" left in active code.

## Remaining / Intentional (not bugs)
- Internal `experiment_id` / `experimentId` still appears as run correlation (job id, logging, progress, some metadata). This is **not** a DB node or filter.
- `schemas/experiment.py` + TS ExperimentRun / ExperimentStatus kept (powers IngestConfig and run metadata).
- Dashboard still surfaces `experiments: {total:0,...}` + empty recent (by design).
- Search history returns empty (document scope moved to Documents view).
- Historical logs / agent-ctx / old upload/*.md contain old references (left as-is).
- Some local function params still named `experimentId` inside documents-view/ingest-view (they mean "the current document/run id").

## Final Status
- `docker compose build` (all services) → success.
- `npx next build` → success.
- Full repo reviewed.
- Experiment concept/node fully excised per redesign.
- Documents page is the canonical view of uploaded/ingested/chunked content.

**Changelog collected from**: git diff --stat / --name-status, repeated build logs (direct + compose), prior session summary traces, source reads of neo4j_client/orchestrator/views/api-client, and live fixes during this review pass.

(End of v1.35 session log)