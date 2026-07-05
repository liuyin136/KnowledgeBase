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
