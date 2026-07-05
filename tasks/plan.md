# Implementation Plan: Document Patch v1.352 — Workflow Fixes + Observability

**Derived from:** upload/Document-patch_v1.352.md (loaded in full)  
**Date:** 2026-07-06  
**Mode:** Planning (read-only exploration completed; no feature code written)  
**Goal:** Break the 6 items into small, vertical, verifiable S/M tasks. Follow skill exactly. Produce `tasks/plan.md` + `tasks/todo.md`.

## Overview
Implement the 6 requested changes from the patch spec:
- Fixes for document delete, dashboard/docs :Knowledge visibility, and Ingest-to-Documents workflow (items 4-6).
- Auto-instrumentation + context propagation across workflow (1-2).
- Log page + :Log DB records (3).

Approach: Vertical slices (complete user-visible paths) ordered by risk/unblock first. Reuse existing patterns (source_file identity, log_pipeline_event + contextvars, TanStack invalidates, thin proxies, sidebar NAV). All verification is manual E2E + build/cypher/grep (project convention). Total change kept small.

## Architecture Decisions & Rationale
- **Delete becomes full source_file purge** (MATCH on source_file only, delete Knowledge + optional KnowledgeChunk). Rationale: fixes the post-ingest 404 (Upload filter was root cause); matches list/dashboard which already aggregate over any Knowledge per source. (Spec assumption confirmed in planner needs.)
- **Context & logging reuse/extend only.** No new deps or tracing framework. Add `document_id` contextvar for clarity (parallel to existing experiment_id). Bind early, reset always, pass explicitly into BackgroundTasks + task entry.
- **:Log is lightweight append-only observation.** Written from events (best-effort). Use simple flat props + optional link via source_file. No indexes initially.
- **Vertical over horizontal:** One slice = working delete flow (DB+API+UI+verify). Then visibility, then workflow glue, then observability layers.
- **UI integration minimal:** Extend ViewKey + NAV + page conditional + one new view file reusing table/card patterns from documents-view/memory-view.
- **No test framework additions.** Manual checks + one "runnable self-check" comment per spec.
- **Invalidates always paired:** documents + dashboard together on mutations.
- **Order:** Fixes first (unblocks), instrumentation second (on working flow), durable Log UI last.

## Dependency Graph (bottom-up order respected)
```
Neo4jClient (delete/list/create_log + context in logs)
  │
  ├── Backend API (documents.py delete/get, new logs.py, ingest start, router include)
  │     │
  │     ├── api-client.ts (delete already, + logs methods + x-corr header)
  │     │     │
  │     │     └── UI components (documents-view delete+badges, ingest invalidates, new LogsView, sidebar NAV, page.tsx, store ViewKey)
  │
  └── core/logging.py (bind helpers + events) + main middleware + tasks.py + orchestrator (already emits some)
```

## Task List (Vertical Slices)

### Phase 1: Document Lifecycle Fixes (unblock 4,5,6)
Build complete "can delete + see post-ingest docs" paths.

## Task 1: Broaden delete_document in Neo4jClient (XS/S)
**Description:** Change the Cypher in delete_document to remove ALL Knowledge + KnowledgeChunk for the source_file (remove the embedding_method='Upload' filter). Update docstring. Return count of deleted Knowledge.

**Acceptance criteria:**
- [ ] DELETE on post-ingest source_file returns count > 0 and removes nodes (verified by Cypher).
- [ ] Pre-ingest (Upload only) still works.
- [ ] No other callers broken (grep for delete_document).

**Verification:**
- [ ] Manual: upload .md, ingest, cypher count before/after delete via backend or neo4j browser.
- [ ] Build: python -m py_compile backend/app/db/neo4j_client.py
- [ ] No regression on list_documents/dashboard_stats.

**Dependencies:** None
**Files likely touched:**
- `backend/app/db/neo4j_client.py`
**Estimated scope:** Small (1 file)

## Task 2: Wire full delete in documents API + update callers (S)
**Description:** Ensure /documents/{id} DELETE uses the broadened client. (Already thin wrapper.) Add/keep the 404 when count==0. Update any comments. Ensure documents-view + ingest-view call paths remain compatible.

**Acceptance criteria:**
- [ ] API returns {"deleted":true, "count": N} for full purge.
- [ ] Non-existent still 404s.

**Verification:**
- [ ] curl or UI delete + check response + Cypher.
- [ ] `docker compose build backend` or equiv.

**Dependencies:** Task 1
**Files likely touched:**
- `backend/app/api/v1/documents.py`
**Estimated scope:** Small (1 file)

## Task 3: Add delete action to Documents page + consistent invalidates (M)
**Description:** In documents-view.tsx, add delete button (modeled on ingest-view's UploadDocumentCard + AlertDialog). On success: toast, invalidate ["documents","dashboard"], refresh list, clear selection if needed. Also ensure ingest-view onDeleted + success paths explicitly invalidate both keys (clean dup if present).

**Acceptance criteria:**
- [ ] Delete from Documents list view succeeds and list updates immediately.
- [ ] Dashboard count drops.
- [ ] Works for both pre- and post-ingest docs.

**Verification:**
- [ ] Full: Ingest view upload + ingest + switch to Documents + delete row + counts zero + no nodes left.
- [ ] npx next build succeeds.

**Dependencies:** Task 2
**Files likely touched:**
- `src/components/rag/views/documents-view.tsx`
- `src/components/rag/views/ingest-view.tsx` (invalidate review)
**Estimated scope:** Medium (2 files)

## Task 4: Align documents load + dashboard visibility for ingested Knowledge (M)
**Description:** Ensure get_document_text(..., "any"), list_chunks_for_source_file, list_documents, and _knowledge_to_document prefer/show ingested (LongText) data. Render representativeEmbeddingMethod / kinds badges in documents list + detail. Tighten comments (":Knowledge"). Remove lingering experimentId assumptions in UI state for docs view. Dashboard stats already counts source_file — verify it surfaces post-ingest.

**Acceptance criteria:**
- [ ] Post-ingest doc selected in Documents loads full parent text + chunks (no "cannot load").
- [ ] List shows badge distinguishing Upload vs LongText/ChildChunk.
- [ ] Dashboard documents/chunks numbers increase after ingest.

**Verification:**
- [ ] Upload → ingest → open in Documents page → see knowledge row + children + badges.
- [ ] Dashboard card updates.

**Dependencies:** Task 3 (for delete+refresh)
**Files likely touched:**
- `backend/app/db/neo4j_client.py` (comments/tweaks if any)
- `backend/app/api/v1/documents.py` (text/chunks paths)
- `src/components/rag/views/documents-view.tsx`
- `src/components/rag/views/dashboard-view.tsx` (if badge or label tweak)
**Estimated scope:** Medium (3-4 files)

### Checkpoint: After Tasks 1-4
- [ ] Delete works end-to-end (pre + post ingest); 0 nodes after delete.
- [ ] Dashboard + Documents list show ingested :Knowledge records and counts.
- [ ] Full upload → ingest → visible in both views.
- [ ] Builds clean (backend + frontend).
- [ ] Human review before observability work.

## Task 5: Ensure Ingest→Documents refresh + state (S)
**Description:** Audit all success paths (ingest status effect, documents create, delete). Guarantee paired invalidates for ["documents", "dashboard"]. Optionally enhance list response or UI to surface latest state per source_file. Minor label updates ("uploaded source files" → note richer post-ingest).

**Acceptance criteria:**
- [ ] After completed ingest, both views refresh without manual reload.
- [ ] Selecting doc shows ingested parent (kind=any path).

**Verification:**
- [ ] Browser loop + refetch checks.

**Dependencies:** Task 4
**Files likely touched:**
- `src/components/rag/views/ingest-view.tsx`
- `src/components/rag/views/documents-view.tsx`
**Estimated scope:** Small

### Phase 2: Context Propagation + Auto-Instrumentation (1+2)

## Task 6: Extend logging.py with document context + convenience (S)
**Description:** Add `_document_id_var`, `bind_document_id`, `reset_document_id`. Update JSONFormatter to include it. Add optional helper or document example in log_pipeline_event calls. Keep existing experiment/correlation.

**Acceptance criteria:**
- [ ] document_id appears in JSON logs when bound.
- [ ] Existing behavior unchanged.

**Verification:**
- [ ] Start server, trigger ingest, inspect a log line.

**Dependencies:** None (can parallel base)
**Files likely touched:**
- `backend/app/core/logging.py`
**Estimated scope:** Small (1 file)

## Task 7: Thread ids + emit events through ingest/workflow (M)
**Description:** 
- In api/v1/ingest.py start: capture/bind before background add_task; pass ids.
- In workers/tasks.py: bind at entry of run_ingest_task (before/around asyncio.run), use in all logs.
- Add consistent `log_pipeline_event` at key boundaries (already partial in orchestrator): upload create, task start/done, delete, documents list response, dashboard.
- Ensure error paths carry ids.
- In main.py error paths + middleware (bind experiment if available via header or body).

**Acceptance criteria:**
- [ ] One full ingest run has >=8 distinct events with correlation_id + document_id (or experiment_id) visible in logs.
- [ ] Ids survive into orchestrator stages and neo4j_client calls.

**Verification:**
- [ ] `docker logs ... | grep -E 'event|document_id|correlation_id'` after trigger.

**Dependencies:** Task 6
**Files likely touched:**
- `backend/app/api/v1/ingest.py`
- `backend/app/workers/tasks.py`
- `backend/app/core/logging.py` (minor)
- `backend/app/api/v1/documents.py`, `dashboard.py` (add a few events)
- `backend/app/main.py`
- `backend/app/db/neo4j_client.py` (optional event wrappers on hot paths)
**Estimated scope:** Medium (4-5 files)

## Task 8: Send x-correlation-id from frontend on all calls (S)
**Description:** Update src/lib/api-client.ts (or a central request fn) to generate/send x-correlation-id header (uuid if missing). Reuse from response if echoed.

**Acceptance criteria:**
- [ ] All backend calls include the header.
- [ ] Logs show it.

**Verification:**
- [ ] Browser devtools network + backend log.

**Dependencies:** Task 7 (for backend side)
**Files likely touched:**
- `src/lib/api-client.ts`
**Estimated scope:** Small

### Checkpoint: After 6-8
- [ ] Traceable logs (ids present end-to-end) for ingest flow.
- [ ] Builds + manual trigger works.
- [ ] No perf hit (log is cheap).

### Phase 3: Log Page + :Log Records (3)

## Task 9: :Log model + Neo4jClient create/list methods (M)
**Description:** Add simple Log pydantic in neo4j_models.py. Implement create_log (CREATE :Log with fields + optional link) and list_logs (filter by document_id/job_id, recent first, limit) in neo4j_client. Use parameterized Cypher. No heavy indexes yet.

**Acceptance criteria:**
- [ ] Can create and retrieve :Log nodes via client.
- [ ] Filters work.

**Verification:**
- [ ] Python snippet or in a log call test: create + list shows it.

**Dependencies:** Task 6-7 (events to feed it)
**Files likely touched:**
- `backend/app/models/neo4j_models.py`
- `backend/app/db/neo4j_client.py`
**Estimated scope:** Medium

## Task 10: Backend logs API + registration (M)
**Description:** Create (or minimal) logs router: GET /logs?documentId=... returns list. Wire create calls from key log_pipeline_event sites or dedicated (best-effort). Include in router.py. Return shape compatible with UI.

**Acceptance criteria:**
- [ ] /api/v1/logs responds with events.
- [ ] After ingest, >=1-3 logs appear for the document.

**Verification:**
- [ ] Hit endpoint or via upcoming UI.

**Dependencies:** Task 9
**Files likely touched:**
- `backend/app/api/v1/logs.py` (new)
- `backend/app/api/v1/router.py`
- `backend/app/api/v1/documents.py` or core (tie-in)
**Estimated scope:** Medium

## Task 11: Frontend logs proxy + api-client + types (S)
**Description:** Add src/app/api/v1/logs/route.ts (thin proxy GET). Extend api-client.ts with logs.list(params). Add minimal TS types if needed (reuse Paginated).

**Acceptance criteria:**
- [ ] Client call succeeds.

**Verification:**
- [ ] Build + simple fetch in console.

**Dependencies:** Task 10
**Files likely touched:**
- `src/app/api/v1/logs/route.ts` (new)
- `src/lib/api-client.ts`
**Estimated scope:** Small

## Task 12: LogsView component (M)
**Description:** New src/components/rag/views/logs-view.tsx . Table of events (timestamp, event, message, ids, json expand). Filter by documentId or recent. Use useQuery on ["logs"...]. Reuse shadcn Table, badge, etc. from documents-view.

**Acceptance criteria:**
- [ ] Renders list after actions.
- [ ] Can filter/see pipeline events.

**Verification:**
- [ ] Navigate (once wired) + see logs from prior ingest.

**Dependencies:** Task 11
**Files likely touched:**
- `src/components/rag/views/logs-view.tsx` (new)
**Estimated scope:** Medium

## Task 13: Wire Logs into navigation + main shell (S)
**Description:** 
- Extend ViewKey in use-ui-store.ts to include "logs".
- Add {key:"logs", label:"Logs", ...} to NAV in sidebar.tsx .
- Import + conditional render in src/app/page.tsx .
- Optional: update mobile nav.

**Acceptance criteria:**
- [ ] "Logs" appears in sidebar; clicking shows view; data loads.

**Verification:**
- [ ] Click nav, see logs table with recent events.

**Dependencies:** Task 12
**Files likely touched:**
- `src/store/use-ui-store.ts`
- `src/components/rag/sidebar.tsx`
- `src/app/page.tsx`
**Estimated scope:** Small

### Final Checkpoint + Polish
- [ ] All 6 spec success criteria met (see patch doc).
- [ ] One full cycle: upload → ingest (with logs) → view in Documents + Logs page → delete → clean + dashboard 0.
- [ ] Logs contain ids; :Log nodes present.
- [ ] Builds (full docker or npx + py_compile).
- [ ] This patch doc updated with shipped note.
- [ ] tasks/ reviewed.

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| Delete now purges ingested data | Med | Confirm with human (in planner needs); document in UI confirm + changelog. |
| Log writes add latency | Low | Best-effort / after event; measure one cycle. |
| Context bind missed in one path | Low | Explicit pass + grep for bind calls in review. |
| Sidebar/ViewKey drift | Low | Single source (store) + small diff. |
| Post-redesign experiment remnants | Low | Already cleaned in prior patch; only touch documents paths. |

## Open Questions (also in patch)
See "Planner Needs" section appended to upload/Document-patch_v1.352.md .
Key ones requiring human:
- Delete full purge OK?
- :Log write strategy (auto in event vs explicit)?
- Log nav placement preference?

## Verification Story (overall)
- Per task + final manual E2E described in tasks.
- Use existing docker / npm / python commands.
- Grep logs + Cypher MATCH count for :Knowledge / :Log as ground truth.

**Plan ready for human approval.** Proceed only after review of this + appended needs in the spec. Use incremental-implementation + context from patch for build phase.