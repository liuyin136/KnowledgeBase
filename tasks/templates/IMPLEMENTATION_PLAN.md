# Implementation Plan: [Feature/Project Name]

Copy this template when creating a new plan under `.cursor/plans/`. After creating the plan, update [tasks/plan.md](../plan.md) to point to it.

## Overview

[One paragraph: what and why]

## Prerequisites

- [PHASE_STATUS.md](../PHASE_STATUS.md) row for this phase
- Template spec: `Download/RAG Workflow template/plan-phase-*.md`
- ADRs if touching Neo4j / vault: [docs/decisions/](../../docs/decisions/)
- Trap log for this phase: [docs/pitfalls/](../../docs/pitfalls/) — create `TRAPS-PHASE-N.md` if missing

## Step 1 — Infrastructure and dependencies (if any)

Per [plan-docker-first.mdc](../../.cursor/rules/plan-docker-first.mdc). Skip if mounted code only.

| Change | File | Service |
|--------|------|---------|
| | | |

## Steps 2+ — Application slices

### Step N — [Title]

**Files:** ...

**Acceptance:**
- [ ] ...

**Verify:**
```bash
# pytest or smoke command
```

---

## Skill Exit (mandatory)

| Phase | Skill / action | Exit evidence |
|-------|----------------|---------------|
| pre (optional) | `agent_smoke.py` | `docker compose run --rm api-worker python scripts/agent_smoke.py` |
| BUILD (start) | grep [docs/pitfalls/](../../docs/pitfalls/) | active `TRAPS-PHASE-*.md` + TRAPS-GLOBAL for step keywords |
| BUILD (end) | append trap if non-obvious dead end | entry in phase trap file per [_TEMPLATE.md](../../docs/pitfalls/_TEMPLATE.md) |
| BUILD | `incremental-implementation` + `test-driven-development` | pytest command + pass output |
| DEBUG | `debugging-and-error-recovery` | grep traps → root cause + `.cursor/debug-pending.json` + regression test |
| REVIEW | `@code-reviewer` (only if user requests) | review report |
| SHIP | `shipping-and-launch` | [PHASE_STATUS.md](../PHASE_STATUS.md) row + changelog (note new traps if any) |

Plans without this section: agent must add before BUILD.

---

## Outcome Gates (developer signs only)

Sign **Then** only — ignore step-by-step flows unless debugging.

| ID | Given | When | Then | [ ] |
|----|-------|------|------|-----|
| G1 | | | | |
| G2 | | | | |
| G3 | | | | |

**Verify command:**

```bash
# one-liner
```
