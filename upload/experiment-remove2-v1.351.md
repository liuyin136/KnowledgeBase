# Experiment Node Label Final Deletion in Live Neo4j (v1.351)

**Date:** 2026-07-06  
**Workspace:** D:\KnowledgeBase2 (branch: v1.3-replace)  
**Trigger:** User: "想在neo4j刪除node label experiment." (following the v1.35 code-level removal of the entire Experiment concept).  
**Outcome:** Live Neo4j DB now has **zero** `:Experiment` nodes, **zero** related constraints, and **zero** stray `experiment_id` properties on other nodes. Only the six clean constraints for Knowledge / KnowledgeChunk / UserQuery* / Memory* remain. Reusable Python cleanup script added for future runs.

## Session Goal
- Physically delete the `:Experiment` label and all associated data from the running Neo4j instance (container `raglab-neo4j`).
- Drop the lingering `experiment_id` uniqueness constraint that the old schema used to create.
- Clean any orphaned `experiment_id` properties that might still exist on `:Knowledge` or other nodes from pre-v1.35 data.
- Provide a repeatable, scriptable way to do this (matching the style of `scripts/init_neo4j.py`).
- Verify with authoritative Cypher (`MATCH count`, `SHOW CONSTRAINTS`).
- Keep the change minimal and reversible in spirit (idempotent commands using `IF EXISTS` / `DETACH DELETE`).
- Document the final physical removal step so future agents/humans know the DB state was explicitly purged after the code purge.

## Context from Prior Pass (v1.35)
- Code, routes, models, Cypher in `neo4j_client.py`, orchestrator, init scripts, frontend TS init route, and docs were cleaned so that **no new** `:Experiment` nodes or `experiment_id` properties on graph nodes are ever written.
- `Experiment` enums and `experimentId` (as internal run correlation / job tag) were intentionally kept for logging, progress, and API response shapes.
- However the **live database** still carried the old constraint (`"experiment_id"` for `[:Experiment]`) even when node count was already 0 (from previous manual or failed runs).
- Old logs showed many `UNRECOGNIZED` warnings from queries that referenced `e.status`, `e.kind`, `e.created_at` on a non-existent label.

## Actions Taken (2026-07-06)

### 1. Pre-check state of live DB
```powershell
docker compose ps          # confirmed neo4j healthy + running
docker compose exec -T neo4j cypher-shell ... "MATCH (e:Experiment) RETURN count(e)"
# → 0
docker compose exec -T neo4j cypher-shell ... "SHOW CONSTRAINTS YIELD name, labelsOrTypes WHERE ... 'Experiment'"
# → "experiment_id", ["Experiment"], "UNIQUENESS"
```

### 2. Execute the purge (single atomic-style block)
```cypher
MATCH (e:Experiment) DETACH DELETE e;
DROP CONSTRAINT experiment_id IF EXISTS;

-- Also sweep any leftover experiment_id props (belt + suspenders)
MATCH (n) WHERE n.experiment_id IS NOT NULL REMOVE n.experiment_id;
```

Executed via:
```powershell
docker compose exec -T neo4j cypher-shell -u neo4j -p P@ssw0rd --format plain "..."
```

### 3. Post-verification (multiple angles)
- `MATCH (e:Experiment) RETURN count(e)` → **0**
- `SHOW CONSTRAINTS` (full) → only the 6 expected:
  - knowledge_id, knowledgechunk_id, userquery_id, userquerychunk_id, memory_id, memorycart_id
- Targeted check for any remaining Experiment constraints → **0**
- Sweep for stray properties → `nodes_with_experiment_id_prop` → **0**

### 4. Created reusable cleanup script
Added `backend/scripts/cleanup_experiment.py` (modeled directly on `init_neo4j.py`):
- Uses the same `Neo4jClient` + settings.
- Prints before/after counts.
- Does `DETACH DELETE`, `DROP CONSTRAINT ... IF EXISTS`, extra `SHOW CONSTRAINTS` scan for any Experiment-named constraints.
- Idempotent and safe to re-run.
- Usage:
  ```powershell
  docker compose run --rm backend python scripts/cleanup_experiment.py
  ```

The script lives alongside `init_neo4j.py` so operators have a matching pair (init vs. historical cleanup).

## Key Design / Ponytail Choices
- Used **direct cypher-shell** for the live deletion (no image rebuild required for the immediate task).
- The Python script follows the existing pattern (import sys path hack, Neo4jClient, settings) — no new abstractions.
- Commands are **idempotent** (`IF EXISTS`, `DETACH DELETE` on possibly empty set).
- Did **not** touch the in-memory `experiment_id` correlation values (still used by jobs, progress, logs, `ExperimentRunMetadata`, etc.).
- Did **not** delete historical log files or old agent-ctx docs — they are archaeological.
- Deletion of nodes first, then constraint (order matters less when count==0, but documented).
- Verification uses the exact same `SHOW CONSTRAINTS` shape that `init_neo4j.py` and the frontend `/neo4j/init` route rely on.

## Files Touched in This Pass
- **New:** `backend/scripts/cleanup_experiment.py` (the durable tool)
- **Executed (not source):** live Cypher against `raglab-neo4j`
- Minor cross-checks against `docker/docker-compose.yml` (container name, auth, health), `backend/scripts/init_neo4j.py`, and previous `neo4j_client.py` changes.

## Final DB Architecture State (Neo4j)
Labels in use:
- Knowledge, KnowledgeChunk, UserQuery, UserQueryChunk, Memory, MemoryCart

Constraints: exactly the six uniqueness constraints listed above.  
No vector or fulltext indexes reference Experiment.  
No code path (backend or frontend init) will ever emit a `CREATE CONSTRAINT ... Experiment`.

## How to Re-run / Re-verify (for future agents or operators)
1. Ensure stack is up: `docker compose up -d`
2. Quick manual:
   ```powershell
   docker compose exec -T neo4j cypher-shell -u neo4j -p P@ssw0rd --format plain \
     "MATCH (e:Experiment) DETACH DELETE e; DROP CONSTRAINT experiment_id IF EXISTS;"
   ```
3. Full scripted (after any rebuild that includes the script):
   ```powershell
   docker compose run --rm backend python scripts/cleanup_experiment.py
   ```
4. Always verify:
   ```cypher
   MATCH (e:Experiment) RETURN count(e);
   SHOW CONSTRAINTS;
   ```

## Outcome Summary
The "rebuild without experiment" is now **physically complete** at both layers:
- Code & schema definitions (v1.35)
- Live database instance (v1.351)

`:Experiment` is gone from the graph. The name `experiment_id` survives only as an internal correlation identifier for jobs/runs (intentionally kept, never stored as a node property anymore).

**Changelog note for this micro-pass:** Final physical purge of historical `:Experiment` data + constraint + stray props + added matching cleanup script. All verifications passed with zero remaining artifacts.

(End of v1.351 session log)