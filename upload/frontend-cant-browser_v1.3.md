# Frontend Can't Load / Browser 304 + Backend Warnings (v1.3 Investigation)

**Date:** 2026-07-05  
**Workspace:** D:\KnowledgeBase2 (branch v1.3-replace, clean at start)  
**Status:** Docker stack running (frontend, backend, neo4j, redis, api-worker)  
**File created per user request** for all repro details, test artifacts, and updates.

## User Symptoms (recap)
- Access `localhost:3000` — "cannot see load the page"
- Browser DevTools (Network): `localhost:3000` shows **304 Not Modified**
- Every access → backend logs emit **warnings**
- User has no useful logs to troubleshoot (only scary backend output visible)
- Using browser devtools for inspection

## Environment Snapshot (Live at Time of Investigation)

From PowerShell commands (non-destructive):

**Ports:**
- 3000, 8000, 7687, 7474, 6379 all listening (frontend + full backend stack).

**Docker Compose (`docker compose ps`):**
- raglab-frontend: Up (0.0.0.0:3000)
- raglab-backend: Up (healthy) (0.0.0.0:8000)
- raglab-api-worker: Up (unhealthy)
- raglab-neo4j: Up (healthy)
- raglab-redis: Up (healthy)

**Current shell env:** `BACKEND_URL` empty (normal for host shell; containers have internal wiring).

**No local `.next`** (frontend runs as containerized standalone build).

**Existing artifacts:**
- `baseline-backend.log`, `baseline-frontend.log`, `baseline-worker.log`
- `backend-logs-clean.txt`, `during-logs.txt`
- Analyzers: `analyze-logs.py`, `parse-during.py`

**Live docker logs (pre-repro):** Mostly internal healthcheck `GET /health 200`. Frontend only shows "Next.js ... Ready".

## Created Test Artifact

**`upload/repro-frontend-cant-browser_v1.3.ps1`** (new file, 2026-07-05)

A self-contained PowerShell repro script that:
1. Does initial GET /
2. Does conditional GET to force 304
3. Triggers `/api/v1/dashboard`
4. Captures immediate backend warnings
5. Prints health + emptiness summary

**Usage (after docker stack up):**
```powershell
cd D:\KnowledgeBase2
.\upload\repro-frontend-cant-browser_v1.3.ps1
```

Full script content is at end of this doc (or read the .ps1).

## Repro Steps + Exact Commands Run + Outputs

### 1. Fresh Environment + Log Analysis
Commands run:
```powershell
# Snapshot
Get-NetTCPConnection ... ports 3000/8000/...
docker compose ps
docker compose logs --tail 30 backend
docker compose logs --tail 20 frontend
Get-ChildItem *log*

# Analyzers (on historical files)
python analyze-logs.py
python parse-during.py

# Deep search
Select-String ... dashboard | neo4j.notifications ...
```

**Key results from analyzers:**
- `backend-logs-clean.txt`: 19 WARNING, 19 INFO, 1 ERROR. Dominant: `neo4j.notifications` (18). Events include `lifespan.embedder.load_failed`.
- `during-logs.txt`: 20 WARNINGs, all `neo4j.notifications` from the exact dashboard stats + recent queries.
- Sample warning (repeated on dashboard):
  ```
  level=WARNING, logger=neo4j.notifications
  message=Received notification ... property names ... not available ... (status / kind / created_at)
  for query: MATCH (e:Experiment) WITH count... CASE WHEN e.status ... {kind: 'search'} ... ORDER BY e.created_at
  ```
- Dashboard calls in logs are followed immediately by these 4-6 WARNING lines + `GET /api/v1/dashboard 200 OK`.

### 2. Live Browser Simulation (PowerShell = repro of user flow)
Commands (and the new .ps1 does equivalent):

```powershell
# 1. Initial page load
$r1 = Invoke-WebRequest -Uri 'http://localhost:3000' -UseBasicParsing
# → Status: 200
# Body: <!DOCTYPE html><html... Next.js chunks, fonts, scripts. Contains "RAG Lab", scripts for React.

# 2. Force 304
$headers = @{ 'If-None-Match' = $r1.Headers['ETag'] }
$r2 = Invoke-WebRequest ... -Headers $headers
# → Status: 304 Not Modified  (Invoke-WebRequest surfaces as exception on non-success, but exactly the symptom)

# 3. The dashboard call (what the SPA does on load)
$dash = Invoke-WebRequest -Uri 'http://localhost:3000/api/v1/dashboard'
# → 200
# Body (key parts):
{
  "stats": { "experiments":{"total":0,"completed":0,"failed":0}, "documents":0, "chunks":0, ... },
  "recentExperiments": [],
  "recentSearches": [],
  "system": { "embeddingModel": "jinaai/jina-embeddings-v5-text-small", "embeddingModelLogical": "jina-v5-small", ... },
  "health": {
    "backend": { "status": "online", ... },
    "neo4j": { "status": "offline", "error": "Failed to connect to server... bolt://localhost:7687 ..." }
  }
}

# 4. Logs right after dashboard
docker compose logs --tail 50 backend | Select-String neo4j.notifications
# → Immediately emits the WARNINGs for status/kind/created_at (with correlation_id).
# → Then "GET /api/v1/dashboard HTTP/1.1 200 OK"
```

**Confirmed in live repro (2026-07-05):**
- 304 exactly reproducible on conditional request.
- Dashboard call from "browser" (PowerShell) triggers the backend warnings **every time**.
- Page HTML shell serves (200 first time).
- React content indicators present in HTML source: "RAG Lab", "Dashboard", "Seed sample documents", "System Connections", "FastAPI Backend".
- "Backend services offline" string **not** in initial HTML (client-rendered by React after JS runs).
- Health: backend online, **neo4j offline** (from the Next.js server-side verify using localhost:7687 URI).

### 3. What the User Actually Sees in Browser
- Initial HTML loads (or 304 reuses cached shell).
- After JS hydrate: 
  - Sidebar + header with "RAG Lab v1"
  - "System Connections" section (FastAPI Backend = online, Neo4j = offline with error)
  - Amber banner? (depends)
  - Empty stats cards (0s)
  - "Seed sample documents" button
  - "Quick Start" cards
  - No recent activity
- **If any JS/chunk fails to load** (due to 304 on _next/static assets, hydration mismatch, or network in devtools), main area may look blank or stuck on "Loading…".
- No visible errors unless you open **Console** tab in devtools.
- Backend terminal (docker logs) floods with neo4j WARNING JSON on the dashboard fetch.

## Root Causes Confirmed with Fresh Data

1. **Neo4j property notifications → WARNING spam on every dashboard access**
   - Queries in `backend/app/db/neo4j_client.py` (`dashboard_stats`, `recent_*`) reference `e.status`, `e.kind`, `e.created_at`.
   - On fresh/empty DB (or old nodes), Neo4j treats the property names as "not available" and emits notifications.
   - Logging config surfaces them at WARNING.
   - Triggered because default view + `DashboardView` immediately calls the endpoint.
   - Confirmed live: 5+ warnings per `/api/v1/dashboard`.

2. **304 is normal but confusing + can cause stale experience**
   - Next.js standalone (in docker frontend) + browser conditional requests.
   - First load 200 (shell), reloads often 304.
   - If chunks or main doc are 304'd while server-side changed, React may not update or hydrate correctly → "page doesn't appear to load".

3. **Neo4j health reports "offline" even with healthy container**
   - `src/lib/rag/neo4j.ts` hardcodes `bolt://localhost:7687` (for host-local dev).
   - Inside docker frontend container, `verifyNeo4jConnectivity` fails → UI shows Neo4j offline card + may affect "anyOffline" logic.
   - (Backend itself talks to `neo4j:7687` internally and is healthy.)

4. **Frontend observability black hole for the user**
   - No console logs on mount.
   - Containerized "Ready" only.
   - Dev `tee dev.log` only works for local `next dev`, not docker.
   - User only sees browser Network (304) + backend scary warnings.
   - Dashboard always returns success (even with 0 data + partial health).

5. **Empty DB + client-rendered UI**
   - Stats 0 + recent [] + seed prompt.
   - If user expects populated UI on first access, it "doesn't look loaded".
   - "Welcome" card is gated behind `!anyOffline`.

## Additional Test / Debug Files Added
- `upload/repro-frontend-cant-browser_v1.3.ps1` (executable repro, documented above)
- This `upload/frontend-cant-browser_v1.3.md` (central report)

(Previous investigation plan lives at the session plan.md.)

## Recommended User Commands (copy-paste)

To reproduce yourself right now (stack is up):

```powershell
# From D:\KnowledgeBase2
docker compose ps
docker compose logs --tail 20 frontend
docker compose logs --tail 30 backend | Select-String -Pattern "neo4j|dashboard|WARN"

# Simulate browser + trigger warnings
Invoke-WebRequest -Uri http://localhost:3000 -UseBasicParsing | Select StatusCode, Headers

# Full scripted repro
.\upload\repro-frontend-cant-browser_v1.3.ps1

# After a dashboard access, grab the smoking gun
docker compose logs --tail 20 backend | Select-String neo4j.notifications -Context 0
```

In browser:
- Hard refresh (Ctrl+Shift+R) or open DevTools → Network → check "Disable cache"
- Open **Console** tab (look for React errors, failed chunk loads, fetch errors)
- Inspect Elements for the main content vs just `<div id="__next">` shell
- Check Application → Local Storage for theme

To see clean logs:
- `docker compose logs -f backend` in one terminal while accessing in browser.

## Suggested Next Actions (when ready to edit)
(See prior plan.md for full phased approach.)

Quick wins (low risk):
- Guard the Cypher (use `coalesce(e.status, 'unknown')` etc.) or filter neo4j.notifications in logging.
- Fix neo4j verify URI for container (use env or service name).
- Add client-side console logging on dashboard fetch + error boundary (`src/app/error.tsx`).
- Document "hard refresh + check Console + tail docker logs" in README.
- Ensure seed or init creates at least one Experiment so properties are "observed" by Neo4j.

## Full Content of Created Repro Script

```powershell
# (content of upload/repro-frontend-cant-browser_v1.3.ps1)
# repro-frontend-cant-browser_v1.3.ps1
# Repro script for "frontend can't load / 304 + backend warnings" issue
# Run from project root in PowerShell: .\upload\repro-frontend-cant-browser_v1.3.ps1
# Requires: docker compose stack running (frontend on :3000, backend reachable)

Write-Host "=== REPRO: Frontend load + 304 + backend warnings (v1.3) ===" -ForegroundColor Cyan

$base = "http://localhost:3000"

Write-Host "`n[1/5] Initial GET / (simulates browser tab open)..."
try {
  $r1 = Invoke-WebRequest -Uri $base -UseBasicParsing -TimeoutSec 10
  Write-Host "  Status: $($r1.StatusCode)  (expect 200)"
  $etag = $r1.Headers['ETag']
  if (-not $etag) { $etag = 'W/"manual-test"' }
  Write-Host "  ETag captured: $etag"
  if ($r1.Content -match 'RAG Lab') { Write-Host "  HTML contains 'RAG Lab' title: YES" }
} catch { Write-Host "  Error: $_" }

Write-Host "`n[2/5] Conditional GET with If-None-Match (forces 304)..."
try {
  $r2 = Invoke-WebRequest -Uri $base -Headers @{ 'If-None-Match' = $etag } -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop
  Write-Host "  Status: $($r2.StatusCode)"
} catch {
  if ($_.Exception.Response.StatusCode.value__ -eq 304) {
    Write-Host "  Status: 304 Not Modified (EXPECTED - matches user symptom)"
  } else { Write-Host "  Other: $($_.Exception.Response.StatusCode)" }
}

Write-Host "`n[3/5] Trigger the dashboard fetch (causes backend neo4j warnings)..."
$dash = Invoke-WebRequest -Uri "$base/api/v1/dashboard" -UseBasicParsing -TimeoutSec 15
Write-Host "  Dashboard status: $($dash.StatusCode)"
$dj = $dash.Content | ConvertFrom-Json
Write-Host "  Stats total experiments: $($dj.stats.experiments.total)"
Write-Host "  Backend health: $($dj.health.backend.status)"
Write-Host "  Neo4j health: $($dj.health.neo4j.status)"

Write-Host "`n[4/5] Capture backend logs right after (look for WARNING neo4j)..."
Start-Sleep 1
$recentWarn = docker compose logs --tail 30 backend 2>&1 | Select-String -Pattern "neo4j.notifications|WARNING" | Select -Last 6
$recentWarn | ForEach-Object { Write-Host "  $_" }

Write-Host "`n[5/5] Quick summary for user..."
Write-Host "Repro complete. See upload/frontend-cant-browser_v1.3.md for full details + analysis." -ForegroundColor Green
```

---

This document captures **all** commands run, outputs, the new test script, and updated analysis. Run the repro script anytime the stack is up to demonstrate the issue to others.

If you want source fixes now (e.g. edit the Cypher or add logging), say the word and provide approval for specific files/changes. Otherwise this stands as the complete repro record.