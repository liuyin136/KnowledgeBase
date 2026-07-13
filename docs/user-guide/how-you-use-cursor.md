# How to use Cursor in KnowledgeBase3

For humans orchestrating AI agents. Agents start at [AGENTS.md](../../AGENTS.md).

---

## Modes

| Mode | Use when | Agent can edit? |
|------|----------|-----------------|
| **Ask** | Questions, architecture, review read-only | No |
| **Plan** | DEFINE / PLAN — spec and implementation plan | Plan files only |
| **Agent** | BUILD / DEBUG / SHIP | Yes |
| **Debug** | Reproduce runtime bug with instrumentation | Yes (debug flow) |

---

## Lifecycle keywords (paste into message)

```
DRAFT: 我想做 X，還沒定義範圍 (ask mode)
DEFINE: 依 template plan-phase-N，寫 spec + Outcome Gates (plan mode)
PLAN: DEFINE 通過後，拆 step；Docker 改動放 Step 1 (agent mode)
BUILD: 執行 tasks/plan.md 指向的 .cursor/plans 的 Step N (AGENT mode)
DEBUG: [症狀]；先讀 docs/pitfalls/、docs/incidents/、ADR Wrong patterns
REVIEW: @code-reviewer 未 commit diff
SHIP: pytest 過 + Outcome Gate 勾選 + 更新 PHASE_STATUS 一行
```

---

## File map (read order)

```
AGENTS.md
  → tasks/PHASE_STATUS.md        (做到哪)
  → Download/RAG Workflow template/  (spec canon)
  → tasks/plan.md                (active plan 指標)
  → .cursor/plans/*.plan.md      (implementation plan — BUILD 用)
  → tasks/CP-*-E2E.md            (Outcome Gates — 你只簽 Then)
  → docs/decisions/ADR-*.md      (永不犯的規則)
  → docs/incidents/INC-*.md      (已關閉的 bug)
  → docs/pitfalls/TRAPS-*.md     (BUILD 中途陷阱 — grep 每 step)
```

**Conflict:** template wins over `.cursor/plans/` on requirements.

---

## Attach in messages

| Attach | When |
|--------|------|
| `@code-reviewer` | REVIEW before merge |
| `@security-auditor` | Security-sensitive change |
| `ADR-002` path or 「依 ADR-002」 | delete / purge / clear index |
| `ADR-004` path or rerank embed errors | n_batch / n_ctx alignment |
| Skill name | Force workflow (e.g. planning-and-task-breakdown) |

---

## BUILD workflow

1. Confirm [tasks/plan.md](../../tasks/plan.md) points to active `.cursor/plans/*.plan.md`.
2. Optional smoke:

   ```bash
   docker compose run --rm api-worker python scripts/agent_smoke.py
   ```

3. Tell agent: `BUILD step N per active plan`.
4. Agent greps [docs/pitfalls/](../../docs/pitfalls/) at step start; appends trap entry at step end if non-obvious dead end (Skill Exit).
5. Agent runs pytest from plan **Skill Exit**.
6. You sign **Outcome Gates** in `tasks/CP-*-E2E.md` (Then only).
7. Update [tasks/PHASE_STATUS.md](../../tasks/PHASE_STATUS.md) one line (note new traps if any).

---

## DEBUG workflow

1. Grep [docs/pitfalls/README.md](../../docs/pitfalls/README.md) and active `TRAPS-PHASE-*.md` for similar symptom.
2. Grep [docs/incidents/README.md](../../docs/incidents/README.md) for closed bugs.
3. Agent mode: `DEBUG: [symptom]` + logs.
4. Agent creates `.cursor/debug-session.active` at session start.
5. Agent confirms root cause → writes `.cursor/debug-pending.json`.
6. You use Cursor Debug **Proceed** / **Mark as fixed** on the fix.
7. On agent **stop**, hook:
   - generates `docs/incidents/INC-DRAFT-*.md`
   - if `adr_candidate: true`, also `docs/decisions/ADR-NNN-*.md` (Draft; number from [_registry.json](../../docs/decisions/_registry.json))
   - if `debug-session.active` exists but JSON missing → **WARN on stdout** (reminder to write JSON)
8. You edit INC draft → rename `INC-NNN-*.md` → update [incidents README](../../docs/incidents/README.md).
9. If ADR draft was created → add Wrong patterns → set Status **Accepted** → update [decisions README](../../docs/decisions/README.md).
10. If trap led to INC/ADR → update trap entry **Promote** field with link.

**Limitation:** Hook runs on agent `stop`, not on Debug UI button. Agent must write `debug-pending.json` before stop.

### INC vs ADR vs TRAPS

| Artifact | When | Who writes |
|----------|------|------------|
| **TRAP** | BUILD dead end; lesson not yet a closed bug or policy | Agent append each step (Skill Exit) |
| **INC** | Closed bug with symptom, fix, regression test | DEBUG stop hook → you promote |
| **ADR** | Policy agents must never violate again (`Wrong patterns`) | DEBUG `adr_candidate` or DEFINE |

Set `adr_candidate: true` when the fix encodes a rule (API choice, config invariant, lifecycle). Example: [INC-003](../../docs/incidents/INC-003-rerank-n-batch-512.md) → [ADR-004](../../docs/decisions/ADR-004-jina-rerank-n-batch-alignment.md).

Trap entry shape ([_TEMPLATE.md](../../docs/pitfalls/_TEMPLATE.md)):

```markdown
### [YYYY-MM-DD] Task 2.1 — short title
- **Symptom:** ...
- **Trap:** wrong path tried
- **Do instead:** ...
- **Promote:** — | INC-NNN | ADR-NNN
- **Regression:** optional pytest
```

`debug-pending.json` shape:

```json
{
  "symptom": "...",
  "root_cause": "...",
  "fix_summary": "...",
  "files_touched": ["path"],
  "regression_test": "pytest ...",
  "adr_candidate": true
}
```

---

## What you sign vs ignore

| You sign | You ignore |
|----------|------------|
| Outcome Gate **Then** checkboxes | Flow 1–9 step-by-step |
| PHASE_STATUS Status + Changelog | Full agent diff |
| INC draft → promote or discard | 32 archived cursor plans |
| ADR draft → Accepted + Wrong patterns | Auto-draft wording |
| Trap log grows during BUILD | Agent must append per Skill Exit |

---

## Docker quick reference

| Change | Command |
|--------|---------|
| `backend/app`, worker code | `docker compose restart backend api-worker` |
| API still stale | `docker compose up -d --force-recreate backend` |
| Frontend UI | `docker compose build frontend` |

See [.cursor/rules/docker-build.mdc](../../.cursor/rules/docker-build.mdc).

---

## Plan templates

- Implementation plan: [tasks/templates/IMPLEMENTATION_PLAN.md](../../tasks/templates/IMPLEMENTATION_PLAN.md)
- CP Outcome Gates: [tasks/templates/CP-OUTCOME-GATE.md](../../tasks/templates/CP-OUTCOME-GATE.md)

New plans must include **Skill Exit** and **Outcome Gates** sections.
