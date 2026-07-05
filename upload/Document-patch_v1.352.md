# Document Patch v1.352 — Workflow Fixes + Observability (Auto-Instrument, Logs, Context)

**Status:** SPEC / PATCH PLAN (ready for implementation)  
**Date:** 2026-07-06  
**Branch context:** v1.3-replace (post experiment-remove v1.35)  
**Scope:** 6 items requested. Follows `/documentation-and-adrs`, `/spec-driven-development`, `/context-engineering`, `/code-review-and-quality`, `/using-agent-skills`.  
**Intent:** User will implement based on this. Keep minimal, agent-readable, spec-first. Ponytail: delete over add where possible; reuse existing logging/contextvars; shortest working changes.

**OPTIMIZED AGENT CONTEXT (context-engineering):**
- Load full: this file.
- For fixes 4-6: neo4j_client.py + documents.py + the 3 views (ingest/documents/dashboard).
- For 1-2: logging.py + main.py + tasks.py + ingest.py + api-client.ts.
- For 3: + new logs bits.
- Also load: upload/experiment-remove_v1.35.md (model baseline) + recent worklog tail.
- Hierarchical: source_file = doc identity; all Knowledge per source; Upload placeholder vs LongText/Child post-ingest.
- Do not load: full orchestrator unless touching pipeline stages; no old experiment files.

---

## Objective
Fix 3 critical workflow bugs blocking document lifecycle (upload → ingest → documents/dashboard visibility + delete). Add foundational observability:
1. Auto-instrumentation across the full workflow (ingest, search, documents, dashboard, workers).
2. Improve Context Propagation (builds on existing contextvars in core/logging.py).
3. Persistent Log page + `:Log` label in Neo4j for durable event records (beyond stdout JSON logs).

**Users:** Developer + future AI agents operating the RAG platform.  
**Success looks like:**
- Documents created via ingest or upload always appear in Dashboard + Documents page (counts + lists use `:Knowledge` source_file correctly).
- Delete removes a full document (source_file group) reliably; no 404 after ingest.
- Full end-to-end workflow (Ingest view → background task → Documents view) is visible, logged, and traceable.
- New Log UI + DB records exist and are queryable.
- All changes are reviewable with small diffs.

---

## ASSUMPTIONS (Surface immediately — per spec-driven)
1. Neo4j labels remain `:Knowledge` / `:KnowledgeChunk` (case-sensitive; user shorthand ":knowledge" == this). No return to :Experiment.
2. Delete semantics: full source_file purge is acceptable (ingested data + placeholders). If "keep history" wanted later, add soft-delete.
3. Logging addition uses existing `log_pipeline_event` + contextvars; no new heavy deps unless stdlib/contextvars insufficient.
4. "Log page" = new simple view (like memory-view) + backend list endpoint + `:Log` nodes. Not full ELK.
5. Auto-instrumentation = expand bind + emit at key boundaries (API entry, task start/end, orchestrator stages, DB ops, UI effects) — not OpenTelemetry unless explicitly added.
6. Frontend proxy routes (`src/app/api/v1/...`) stay thin; real logic in FastAPI.
7. Dashboard/Documents load issues are data/query shape (not auth or CORS).
→ Correct now or we proceed.

---

## The 6 Items — Spec-Driven Format (AI-agent easy parse)

Each item has:
- **Problem / Context** (root cause hints from current code)
- **Objective + Success Criteria** (testable)
- **Commands / Verify**
- **Key Files (expected touch points)**
- **Implementation Notes / Boundaries** (from analysis + ponytail)
- **Open Questions**

### 1. Create the Auto-instrumentation for all of the workflow

**Problem/Context:**  
Current: `core/logging.py` has `log_pipeline_event`, `bind_experiment_id`, `bind_correlation_id` (contextvars), middleware for corr-id, and scattered calls in api/*, orchestrator, neo4j_client, tasks.  
Gaps: background tasks, worker entry, full ingest stages, delete path, documents list/get, dashboard, frontend invalidations, error paths. Correlation not always threaded into `run_ingest_task`. No consistent "workflow span" concept. UI console.debug obs exists but not structured.

**Objective:** Every major stage of upload/ingest/search/documents/dashboard emits structured event with ids. Agents/humans can trace a documentId end-to-end from logs.

**Success Criteria:**
- Every ingest run produces >= 8 distinct `event` keys in logs (start, upload, task.start, stages in orchestrator, persist, done, documents.list post-ingest).
- Correlation_id present on all HTTP + propagated to background task logs.
- `experiment_id` (job correlation) bound before task dispatch and inside orchestrator.
- Error paths always include stage + ids (existing `log_error`).
- New Log page (item 3) can surface recent events (at minimum the pipeline.* ones).
- No performance regression on hot paths (log calls are cheap JSON).

**Commands:**
- Dev: `npm run dev` (frontend) + `uvicorn ...` or `docker compose up`
- Trigger: upload .md on Ingest → start ingest → poll status → view Documents + Dashboard.
- Verify: `docker compose logs backend | grep -E 'event|pipeline\.'` or parse `analyze-logs.py` style.

**Key Files:**
- `backend/app/core/logging.py` (expand binders, helpers, auto-bind on entry)
- `backend/app/main.py` (middleware, lifespan bind)
- `backend/app/api/v1/ingest.py`, `documents.py`, `dashboard.py`, `search.py`
- `backend/app/workers/tasks.py` (bind before/after orchestrator)
- `backend/app/services/orchestrator.py` (stage events already good — make consistent)
- `backend/app/db/neo4j_client.py` (wrap key ops with events)
- `src/components/rag/views/ingest-view.tsx`, `documents-view.tsx` (add structured client events if needed; keep console.debug for now)

**Notes (ponytail):**
- Reuse/extend `log_pipeline_event(logger, "workflow.stage", msg, document_id=..., job_id=..., **fields)`.
- Bind at middleware + explicitly pass/rebind into BackgroundTasks + thread for workers.
- Add `bind_document_id` if distinct from experiment_id (or alias).
- One small self-check: after change, one full ingest produces traceable log sequence (add comment with example).
- Prefer contextvars over threading ids in every signature.

**Verify step:** Run ingest, capture logs, assert correlation + 1+ document_id in task/orchestrator events.

**Open:** Do we persist auto-instr events to :Log immediately (see item 3) or only on demand?

### 2. Context Propagation

**Problem/Context:**  
Existing: contextvars `_experiment_id_var`, `_correlation_id_var` + bind/reset helpers + http middleware. Used in some log calls and main error handler.  
Not propagated into:
- FastAPI BackgroundTasks (the `add_task(run_ingest_task, ...)` call site).
- Worker thread / new event loop in `run_ingest_task`.
- All DB writes or orchestrator sub-calls.
- Frontend → no x-correlation-id header on most requests (api-client.ts).

Result: logs after "queued" often lose ids.

**Objective:** Ids flow from HTTP request → job creation → background task → orchestrator stages → neo4j → response headers. Usable for debugging cross-layer.

**Success Criteria:**
- `correlation_id` and `experiment_id` (or document_id) appear in >90% of pipeline.* log lines for a run.
- Inside `run_ingest_task`, the bound values from caller are visible.
- Frontend api calls send `x-correlation-id` (reuse or generate).
- Reset always happens (try/finally).
- Works for both direct uvicorn and api-worker (RQ) paths.

**Key Files:**
- `backend/app/core/logging.py` (maybe `context_scope(**ids)` helper for with-block)
- `backend/app/api/v1/ingest.py` (capture ids, pass + bind before add_task)
- `backend/app/workers/tasks.py` (accept + bind at top of run_ingest_task + inside async)
- `src/lib/api-client.ts` (inject header on requests)
- `backend/app/main.py` (ensure response always echoes)

**Implementation Notes:**
- Pattern (reuse existing):
  ```python
  token = bind_experiment_id(experiment_id)
  try:
      ...
  finally:
      reset_...
  ```
- For background: read current context before add_task, pass explicitly, re-bind inside task.
- Ponytail: one new helper fn `with_correlation(corr, exp, doc_id=None): ...` if it collapses boilerplate. Otherwise keep explicit.
- No new threading.local if contextvars suffices.

**Verify:** Same as #1 — grep logs for missing ids on a traced run.

### 3. Create a Log page and Log Label on database to record

**Problem/Context:**  
Logs are stdout JSON only (good for docker). No UI page. No durable `:Log` nodes. Hard for agents or users to query history of a document without grepping logs.

**Objective:** 
- New `:Log` nodes (or lightweight event records) written for key events.
- `/api/v1/logs` (list + filter by document_id / job_id / event) + frontend Log view (in sidebar?).
- Log page shows recent pipeline events, errors, ingest milestones.

**Success Criteria:**
- Creating a document + ingesting creates >=3 `:Log` nodes linked or tagged with source_file.
- New UI page (or tab) at e.g. `/logs` or via sidebar lists them, filterable.
- Backend schema addition minimal (see neo4j schema patterns).
- Does not slow writes (async or fire-and-forget for log writes, or batch).

**Key Files:**
- `backend/app/models/neo4j_models.py` (add Log model?)
- `backend/app/db/neo4j_client.py` (create_log, list_logs)
- `backend/app/api/v1/` (new logs.py or reuse router)
- `backend/app/api/v1/router.py` (include)
- `src/app/api/v1/logs/route.ts` (proxy)
- `src/components/rag/views/` (new logs-view.tsx or add to settings)
- `src/components/rag/sidebar.tsx` (add "Logs" nav item)
- `src/lib/api-client.ts` (logs api)

**Implementation Notes (spec-driven + docs):**
- Label: `:Log { id, ts, event, message, document_id?, job_id?, experiment_id?, level, payload_json }`
- Or relation `(:Knowledge)-[:HAS_LOG]->(:Log)` for source_file docs.
- Keep write path cheap: reuse log_pipeline_event + side-effect create if flag, or separate service.
- UI: simple table + JSON expand (reuse existing table/ui patterns from documents-view).
- ADR note: we chose Neo4j label over separate log store for single-DB simplicity. Revisit if volume high.
- Ponytail: start with list recent + by documentId only. No complex search yet.

**Commands / Verify:**
- After ingest: `MATCH (l:Log) RETURN count(l), collect(DISTINCT l.event)`
- UI: navigate Log page, see events for the source.

**Open:** Retention policy? TTL on :Log? Manual purge?

### 4. Fix the document cannot delete, dashboard does not show the :knowledge issue

**Problem/Context (root cause analysis):**
- `delete_document(source_file)` in neo4j_client: only `MATCH (k:Knowledge {source_file, embedding_method: 'Upload'}) ... DETACH DELETE`.
- After ingest: additional `embedding_method: 'LongText'` (and ChildChunk) nodes exist for same source_file. Delete returns 0 → 404.
- list_documents / dashboard_stats: `MATCH (k:Knowledge) ... count(DISTINCT k.source_file)` — should see ingested. But if UI or proxy filters oddly, or Upload was primary assumption, "does not show".
- Documents page (ingest list + documents-view) relies on list + chunks/text. Delete button lives only in ingest-view UploadDocumentCard.
- No delete UI on dedicated Documents page.
- Possible stale query cache or missing invalidate after delete in some paths.
- Neo4j warnings (status/kind on Experiment) are red herrings from old redesign.

**Success Criteria:**
- `DELETE /documents/{id}` on a post-ingest document succeeds and removes ALL Knowledge + KnowledgeChunk for that source_file. Returns count > 0.
- After delete: Dashboard documents count decreases; list no longer includes it.
- Dashboard always reflects current `count(DISTINCT source_file)` from any Knowledge.
- Delete from either Ingest card or (added) Documents page works.
- 0 documents left after delete of last one.

**Key Files:**
- `backend/app/db/neo4j_client.py` (fix delete_document — broaden MATCH or two-phase)
- `backend/app/api/v1/documents.py` (delete endpoint; consider ?force or keep current Upload-only as option? — recommend full purge)
- `src/components/rag/views/documents-view.tsx` (add delete action + confirm)
- `src/components/rag/views/ingest-view.tsx` (ensure onDeleted invalidates dashboard + documents fully)
- `backend/app/api/v1/dashboard.py` + client (no change likely)

**Implementation (suggested minimal):**
```cypher
// new delete
MATCH (k:Knowledge {source_file: $source_file})
OPTIONAL MATCH (k)-[:HAS_CHUNK]->(c:KnowledgeChunk)
DETACH DELETE c, k
RETURN count(k) AS deleted
```
- Keep old Upload-only logic? No — replace for simplicity (ponytail: one path).
- Update docstring.
- After successful delete, caller must `invalidateQueries(["documents", "dashboard"])`.
- Add delete button to Documents list rows (consistent with ingest card).

**Verify:** Upload → ingest → delete → dashboard==0 + documents list empty + no nodes in cypher.

### 5. Fix documents page cannot load the :knowledge

**Problem/Context:**
- documents-view uses `api.documents.getText(id, "any")`, `.chunks(id)`.
- Backend: `get_original_knowledge` (Upload), `get_knowledge_by_source(..., prefer_non_upload=True)`, `list_chunks_for_source_file` (any Knowledge).
- Comments say ":knowledge" — but actual label is :Knowledge. Possible mismatch if any hard-coded lowercase or old experimentId filters linger.
- Detail mode / chunks sometimes expect experiment shape remnants.
- After redesign, some queries still reference "experiment" keys internally in UI state.
- Possible empty results if Upload filtered exclusively in text path for ingested docs.
- In list view it works via source_file grouping.

**Success Criteria:**
- On Documents page, selecting a row loads full text (ingested parent preferred) + chunks table.
- Both pre-ingest and post-ingest documents load without "cannot load".
- No console errors or empty "no chunks".
- `kind=any` returns LongText parent when present.

**Key Files:**
- `backend/app/api/v1/documents.py` (get_document_text, get_document_chunks — ensure "any" and list use broad match)
- `backend/app/db/neo4j_client.py` (list_chunks_for_source_file, get_* — already broad in most paths; tighten comments)
- `src/components/rag/views/documents-view.tsx` (state keys, query calls, render for nodeType 'knowledge')

**Notes:**
- Use `kind=any` consistently for Documents detail (already in code).
- Remove any leftover `experimentId` assumptions in chunks response handling.
- Ponytail: the list_documents Cypher + list_chunks_for_source_file are the "working path" — align everything to source_file.

**Verify:** Ingest a doc → open in Documents page → see parent knowledge row + children.

### 6. Fix the workflow in between Ingest to Documents

**Problem/Context:**
- Upload creates Upload placeholder :Knowledge.
- Ingest reads via `get_document_text` (Upload only), then creates LongText + chunks.
- On success: ingest-view invalidates ["documents"].
- But:
  - Dashboard may lag (no explicit invalidate in all success paths).
  - Documents page (separate) may show stale or only Upload view.
  - No automatic refresh of counts/stats after background done.
  - "Documents" label in dashboard/ingest says "uploaded source files" but post-ingest they are richer.
  - Possible race: list sees Upload while task running; after done, two entries conceptually (but grouped by source).
  - Delete + re-upload flow broken in some cases.

**Success Criteria:**
- After successful ingest job: Dashboard stats update (documents/chunks), Documents list reflects new chunks/embedding_method badges.
- Selecting newly ingested doc in Documents shows the ingested LongText parent (not just placeholder).
- Invalidate covers dashboard + documents in ingest success + delete paths.
- Visual: representativeEmbeddingMethod or "kinds" badges distinguish Upload vs LongText.
- End-to-end: upload in Ingest → start → done → switch to Documents/Dashboard → visible and loadable.

**Key Files:**
- `src/components/rag/views/ingest-view.tsx` (onSuccess invalidates + perhaps poll dashboard)
- `src/components/rag/views/documents-view.tsx` (ensure it shows post-ingest data; badges)
- `backend/app/api/v1/documents.py` (_knowledge_to_document already passes representativeEmbeddingMethod + kinds — use in UI)
- `backend/app/db/neo4j_client.py` (list_documents already has some)
- Possibly add a lightweight "touch" or event on ingest complete that frontend can key on.

**Implementation Notes:**
- In ingest success: `qc.invalidateQueries({ queryKey: ["documents"] }); qc.invalidateQueries({ queryKey: ["dashboard"] });`
- Documents list already receives `representativeEmbeddingMethod` and `kinds` — render badges (LongText/ChildChunk/Upload).
- For workflow clarity: documents list should prefer or show the "latest" state per source_file.
- Ponytail: reuse existing "kinds" field; don't invent new state machine.

**Verify:** Full loop in browser + log events + counts match.

---

## Tech Stack / Commands (from current project)
See root README + backend/README + package.json.
- Backend dev: `cd backend; python -m uvicorn app.main:app --reload`
- Frontend: `npm run dev`
- Full: `docker compose up`
- Verify build: `docker compose build`, `npx next build`, python -m py_compile ...
- Cypher check: via neo4j browser or `scripts/init_neo4j.py`

**Project Structure highlights (relevant):**
- `backend/app/{api/v1,db,services,workers,core}`
- `src/components/rag/views/{dashboard-view,documents-view,ingest-view}.tsx`
- `src/app/api/v1/...` (thin proxies)
- `upload/*.md` — historical patch/ADR style docs

---

## Code Style Notes (for patch)
- Python: existing docstrings + pipeline event logs.
- TSX: keep "use client", TanStack Query keys stable, cn(), existing shadcn/ui.
- Cypher: parameterized, source_file as key for docs.
- Always invalidate both ["documents"] and ["dashboard"] together on mutating actions.

---

## Testing / Verification Strategy (spec-driven)
- Manual end-to-end for each of 6 (no framework per existing project rules in agent-ctx).
- One runnable check left behind: after changes, a single ingest + delete cycle + `grep` on logs for events + cypher count(source_file) == 0 post-delete.
- For agents: the success criteria above are the assertions.
- Edge: delete non-existent → 404; ingest empty? (existing validation); dashboard after 0 docs.

**Definition of Done (for these patches):**
- [ ] All 6 items meet their success criteria.
- [ ] Logs contain correlation + ids across layers.
- [ ] No regression on existing upload/ingest/search paths.
- [ ] Doc updated (this file).
- [ ] Small focused diffs.

---

## Boundaries (Always / Ask first / Never)
- **Always:** Invalidate queries for documents+dashboard after mutates. Bind context before cross-boundary calls (task, bg). Use source_file as doc id. Log at stage boundaries with ids.
- **Ask first:** Schema changes to :Log (new properties), adding npm/pip deps for instrumentation, changing delete to soft-delete.
- **Never:** Leak stack in responses. Assume Upload-only for documents after ingest. Hardcode lowercase "knowledge" label. Scatter new conditionals without helper.

---

## Draft Review — Possible Changes (code-review-and-quality output)

**Five-axis preview (what a reviewer should look for when implementing):**

**Correctness:**
- Delete must return >0 for post-ingest sources.
- list_documents/dashboard must count source_files that have only LongText (no Upload).
- Context bind must survive BackgroundTasks + new loop in tasks.py.

**Readability:**
- Keep log calls uniform: `log_pipeline_event(logger, "ingest.stage.xxx", "...", document_id=..., job_id=...)`.
- One delete impl, not branched.

**Architecture:**
- Logging stays in core; no business logic in middleware.
- :Log is append-only observation (like Memory). Do not couple core ingest path to it critically (fire-and-forget or best-effort).
- Reuse `list_documents` grouping logic.

**Security:**
- All new endpoints use existing Depends(get_db). No raw Cypher from user input.
- Log payload: sanitize or limit size (existing JSON).

**Performance:**
- Dashboard + documents list are read-only aggregates — keep OPTIONAL MATCH cheap.
- :Log writes: do not await in hot path if possible (or accept small cost for durability).

**Change sizing:** Target <300 LOC total for the 6 items combined. Split if delete + logs balloon.

**Suggested order (per planning-and-task-breakdown spirit):** fixes 4+5+6 first (unblock), then 1+2 (instrument the now-working flow), then 3 (UI + persistence on top).

**Red flags to avoid in impl:**
- New conditionals in delete path.
- Forgetting finally: reset on contextvars.
- Leaving Upload-only delete + adding a second delete function.

---

## Other Skills That Can Help (from /using-agent-skills)

Per using-agent-skills map:
- **planning-and-task-breakdown**: Decompose the 6 into ordered tasks + todo.md (recommended before coding).
- **observability-and-instrumentation**: Canonical for items 1,2,3 (structured logs, traces, symptom alerts). Use it to flesh Log + auto-instr.
- **debugging-and-error-recovery**: For 4,5,6 — reproduce (upload+ingest+delete), localize (Cypher + queryKey), fix, guard (tests or checks).
- **incremental-implementation**: Build one item at a time, vertical slice (e.g. fix delete → verify dashboard → add one event).
- **doubt-driven-development**: For the delete semantics (full purge vs preserve ingested?).
- **test-driven-development**: If any logic grows, write failing check first (even a small script).
- **code-simplification**: After, run to remove any duplicated invalidate or old Upload assumptions.
- **git-workflow-and-versioning**: Commit per item or logical group with clear messages.

Start sequence for this work: spec (this) → planning-and-task-breakdown → context-engineering (load this file + neo4j_client + views) → (debug or incremental) → review.

Do **not** start with implementation without this spec reviewed.

---

## Context Engineering Notes (optimization applied here)
- This file is the Level-2 artifact: load the whole when working the patch; later load single item sections.
- For future agents: reference this + `upload/experiment-remove_v1.35.md` + `backend/app/core/logging.py`.
- Recommendation: add a short `AGENTS.md` (or extend worklog) with "current patch focus: Document-patch_v1.352" when active.
- Selective: when fixing delete, load only neo4j_client.py:delete + documents.py:delete + ingest-view deleteMutation.

---

## Changelog Entry (example for when shipped)
## [1.352] - 2026-07-xx
### Fixed
- Document delete (full source_file purge; post-ingest works)
- Dashboard / Documents page :Knowledge visibility after ingest
- Ingest → Documents workflow refresh + load
### Added
- Auto-instrumentation events on workflow stages
- Context propagation to background + workers + FE headers
- Log page + :Log nodes

---

**End of spec.**  
Human: review this, approve or correct assumptions/success criteria.  
Then: use `/planning-and-task-breakdown` or proceed to implement slices.

Ponytail comment: This doc itself is the high-leverage artifact. Writing 200 lines here prevents 20× wasted agent cycles later. Smallest change that works will come from following the criteria above exactly.

---

## Planner Needs (appended by /planning-and-task-breakdown)

**What the planner surfaced / requires before or during impl (added to make tasks actionable):**

- Confirm delete semantics: full purge of all :Knowledge + :KnowledgeChunk for a source_file is acceptable and desired (current spec assumes yes; changing from "Upload only" is the fix for post-ingest delete 404). If "preserve ingested history" is wanted, we need soft-delete or archive path instead.
- For :Log: decide on persistence timing — inside `log_pipeline_event` (automatic side-effect) vs explicit calls at key points only? Fire-and-forget or await? (to avoid slowing hot ingest paths).
- :Log node schema details (for model + Cypher): exact props beyond {id, ts, event, message, document_id?, job_id?, experiment_id?, level, payload} ? Any indexes/constraints in init? Relation `(:Knowledge {source_file}) -[:HAS_LOG]-> (:Log)` or standalone?
- Log page placement: new top-level sidebar "Logs" view (like Documents), or subsection in Settings / Documents? (plan assumes top-level for visibility).
- Context id strategy: introduce `bind_document_id` / `document_id` var (distinct from job "experiment_id" correlation), or overload experiment_id? (plan uses document_id where source_file known + experiment_id for job).
- Schema / init impact: does adding :Log require change to scripts/init_neo4j.py or neo4j schema docs? (plan: minimal, no constraint initially unless volume requires).
- FE header: ensure api-client.ts sends x-correlation-id on *all* requests (central wrapper) + regenerate on client if missing.
- Verification constraints: stick to manual E2E (upload+ingest+view+delete + `grep` logs + cypher counts) + `docker compose build` / `npx next build`. No new test files unless human overrides project "no tests" convention.
- Risk callouts for impl: delete is now destructive across Upload+ingested; document in changelog + perhaps a confirm dialog. Invalidate duplication in ingest-view (already present) — clean if possible without behavior change.
- Parallelism: fixes phase can be one agent; observability logging + logs UI can be parallel after base data fixes (but share api-client/sidebar changes — coordinate).
- Output artifacts required: update this patch with "shipped" note; populate tasks/plan.md + tasks/todo.md (done by this planning step); small self-check comment left in logging or delete.

**Tasks generated:** See `tasks/plan.md` (full) and `tasks/todo.md` (checklist). Vertical slices prioritize unblock (4-6) then instrument (1-2) then durable logs UI (3).

Human: please confirm the delete scope and :Log write strategy above before full build starts. Other assumptions from original spec carried forward.

**Planning complete.** Next: human approval of plan → incremental impl per tasks/todo.md using context from this doc.
