# Trap log index

**During BUILD** — non-obvious dead ends, wrong assumptions, and "do this instead" notes. Grep before starting a step or re-entering a phase.

Complements [incidents](../incidents/) (closed bugs) and [decisions](../decisions/) (permanent policy). Escalate when a trap repeats or becomes invariant.

| Log | Phase | Status |
|-----|-------|--------|
| [TRAPS-GLOBAL.md](TRAPS-GLOBAL.md) | Cross-phase | living |
| [TRAPS-PHASE-2.md](TRAPS-PHASE-2.md) | Graph memory (2.0) | living |

**Draft entry:** copy [_TEMPLATE.md](_TEMPLATE.md). Append under the phase file — do not create orphan markdown.

## When to use which artifact

| Situation | Artifact | When |
|-----------|----------|------|
| Explored wrong path during BUILD; fix works but lesson should persist | **TRAP** append | End of BUILD step (Skill Exit) |
| Root cause confirmed; regression test exists | **INC** | DEBUG + stop hook |
| Never violate again (API/schema invariant) | **ADR** Wrong patterns | DEBUG `adr_candidate` or DEFINE |
| Trap promoted to policy | TRAP entry → link ADR; mark **Promote: ADR-NNN** | After ADR Accepted |

## Agent rule (Skill Exit)

1. **BUILD step start:** `rg` / grep this folder + active `TRAPS-PHASE-*.md` for task keywords.
2. **BUILD step end:** if non-obvious trap encountered → append one entry (mandatory per active plan Skill Exit).
3. **DEBUG start:** grep traps before incidents (traps are cheaper context).
4. **SHIP:** if new traps added, mention count in [PHASE_STATUS.md](../../tasks/PHASE_STATUS.md) changelog line.

## Already promoted (do not duplicate as traps)

| Topic | Use instead |
|-------|-------------|
| Neo4j vault purge `delete_*` | [ADR-002](../decisions/ADR-002-vault-neo4j-purge-api.md) |
| Vault index status / clear index | [ADR-003](../decisions/ADR-003-vault-index-status-lifecycle.md) |
| Rerank embed row / n_batch | [ADR-004](../decisions/ADR-004-jina-rerank-n-batch-alignment.md) |
| Orphan nodes after delete | [INC-001](../incidents/INC-001-neo4j-delete-orphan.md) |
| Stale uvicorn / API vs mounted code | [INC-002](../incidents/INC-002-stale-uvicorn-backend.md) |
