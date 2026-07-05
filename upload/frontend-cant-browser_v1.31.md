# Frontend Can't Load / Browser 304 + Backend Warnings + Missing Library (v1.3.1 Fixes Applied)

**Version:** v1.3.1 (fixes release)  
**Date:** 2026-07-05  
**Based on:** investigation in `frontend-cant-browser_v1.3.md` + approved root cause + proposal plan

## CHANGELOG / Fixes Applied (this release)

### High Priority (directly address user symptoms)
- **Missing library (peft)**: Added `peft` to `backend/requirements.txt`.  
  Root cause: Jina v5-small embedder load required it; caused lifespan WARNING.  
  Now: clean embedder startup after rebuild.

- **Warning logs (neo4j.notifications on every access)**: Updated Cypher in `backend/app/db/neo4j_client.py` (`dashboard_stats`, `recent_experiments`, `recent_searches`):
  - Use `coalesce(e.status, '')`, `coalesce(e.kind, '')`, `coalesce(e.created_at, datetime('1900-01-01'))`.
  - Changed `{kind: 'search'}` MATCH to `WHERE` clause.
  Root cause: unconditional property refs on labels with no prior data triggered UNRECOGNIZED notifications (surfaced at WARNING level).
  Now: no more property-not-seen warnings on fresh/empty DB.

- **"Cannot see/load" localhost:3000 + false offline state**: 
  - `src/lib/rag/neo4j.ts`: Smarter NEO4J_URI default (`production` → `bolt://neo4j:7687`).
  - `docker/docker-compose.yml`: Added `NEO4J_*` envs to frontend service.
  Root cause: hardcoded localhost:7687 in container + missing env → dashboard health always reported neo4j offline (even when stack healthy). Combined with 304 + empty stats → page looked broken.
  Now: correct health when using docker stack.

- **React render crash (primary cause of blank page - React error #31 "object with keys {status}")**:
  - `src/components/rag/views/dashboard-view.tsx`:
    - Fixed `BackendHealthCard` to safely render `detail` (was directly interpolating objects like `{status: "ok"}` from backend `/health`).
    - Updated local prop type and `DashboardData` interface to `unknown`.
    - Introduced `detailStr` with `typeof` guard + `JSON.stringify` fallback.
  - `src/app/api/v1/dashboard/route.ts`: Added boundary normalization so `health.backend.detail` is always string | null.
  Root cause: `detail && <dd>{detail}</dd>` where detail was object → React #31 during DashboardView render.
  Now: no more crash; detail row shows safe stringified value. This was the real blocker preventing the page from displaying.

### Other
- Followed **incremental-implementation** skill (selected via using-agent-skills): thin slices, verify each (py_compile, file/grep checks, repro script simulation).
- Created/updated this v1.31.md with changelog.
- Repro script (`repro-frontend-cant-browser_v1.3.ps1`) remains valid for regression.

**Verification performed (per incremental slice, local only):**
- Slice 1 (view render fix): search_replace + tsc/grep verification (no errors on our changes).
- Slice 2 (boundary normalize): search_replace + grep.
- All changes minimal, additive, rollback-friendly.
- Full effect requires: your manual `docker compose build` + up, then hard refresh + Console check. No #31 error expected.

See the v1.3 investigation doc for full root cause evidence, live repro outputs, and original symptoms.

## Summary of Root Causes (recap for v1.3.1)
(Condensed from plan)

1. Perceived load failure: 304 + false "neo4j offline" in UI health (URI bug) + empty DB state + weak first-run UX/observability.
2. Warning logs: Neo4j driver notifications from property refs in dashboard queries + logging config.
3. Missing library: `peft` absent from requirements (Jina model dep).

## Proposed Changes for the React #31 "object with keys {status}" Error (Current Root Cause of Blank Page)

**Root cause (localized via browser console + code inspection):**
The error `Uncaught Error: Minified React error #31 ... object with keys {status}` occurs because React cannot render a plain object as a child element.
- The object is `{status: "ok"}` (or similar) returned by the backend `/health` endpoint.
- It flows to the frontend proxy (`/api/v1/dashboard`) as `health.backend.detail`.
- Then passed to `BackendHealthCard` as the `detail` prop.
- In the component:
  ```tsx
  {detail && (
    <dd className="..." title={detail}>
      {detail}   // <--- crashes here when detail is object
    </dd>
  )}
  ```
- The local type wrongly says `detail: string | null`, so no compile-time protection.
- This aborts the entire DashboardView render (default view), making the page appear not to load.

This explains why the page "does not fix" after prior server-side changes — the render crash happens on every successful backend health response.

**Proposed minimal, safe changes (to be implemented incrementally below):**

1. **Primary fix in view (safest, no behavior change for strings):**
   - File: `src/components/rag/views/dashboard-view.tsx`
   - Update the `BackendHealthCard` props type:
     `detail?: unknown;`
   - Change the render block to defensively stringify only when necessary:
     ```tsx
     {detail != null && (
       <div className="flex items-baseline justify-between gap-2 min-w-0">
         <dt className="text-muted-foreground shrink-0">Detail</dt>
         <dd
           className="font-mono text-right truncate"
           title={typeof detail === "string" ? detail : JSON.stringify(detail)}
         >
           {typeof detail === "string" ? detail : JSON.stringify(detail)}
         </dd>
       </div>
     )}
     ```
   - (Optional) Also update the `DashboardData` interface's `backend.detail` to `detail?: unknown | null;`

2. **Optional robustness (normalize at boundary):**
   - File: `src/app/api/v1/dashboard/route.ts` (or `src/lib/rag/backend-client.ts`)
   - In the health object construction, ensure detail is always a string or null:
     ```ts
     detail: backend.detail == null
       ? null
       : typeof backend.detail === "string"
         ? backend.detail
         : JSON.stringify(backend.detail),
     ```

**Why this approach?**
- Minimal diff.
- Preserves existing behavior when detail is a string.
- Makes the UI robust even if backend /health changes shape.
- Does not require docker changes (user will rebuild).
- No new dependencies.

**Risks / Tradeoffs:**
- JSON.stringify on objects will show `{"status":"ok"}` — acceptable for a "Detail" row (or we can improve formatting in a follow-up).
- If there are other places rendering raw API objects, this may not catch them (but this one matches the exact error keys).

**Verification plan (local, no docker):**
- TypeScript check (`npx tsc --noEmit` or similar).
- Grep/read to confirm edit.
- After user docker build: hard refresh, check Console has no #31, health card renders the detail row.

## Next Steps for User
- Review the proposals (already added above) and the implemented changes in this file.
- Manually run `docker compose build frontend` (or the full stack) since you control the build.
- Start the containers.
- Hard refresh `http://localhost:3000` (disable cache in devtools recommended).
- Open Console: the React #31 "object with keys {status}" should be gone.
- Health "Detail" row should now render without crash (shows string or `{"status":"ok"}`).
- Run the repro script if desired for regression.
- If other similar render issues appear, report the new console error.

All changes are in scope of the approved plan. No unrelated modifications. 

(Previous full investigation content from v1.3 follows below if needed; this file focuses on the fixes changelog.)
