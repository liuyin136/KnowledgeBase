# Task Checklist: Document Patch v1.352 (from plan.md)

Follow tasks/plan.md for details. Mark complete only after acceptance + verification for that task. Checkpoints are gates.

## Phase 1: Document Lifecycle Fixes (unblock visibility + delete)
- [ ] Task 1: Broaden delete_document in Neo4jClient
- [ ] Task 2: Wire full delete in documents API + update callers
- [ ] Task 3: Add delete action to Documents page + consistent invalidates
- [ ] Task 4: Align documents load + dashboard visibility for ingested Knowledge

### Checkpoint: After Tasks 1-4
- [ ] Delete works end-to-end (pre + post ingest); 0 nodes after delete.
- [ ] Dashboard + Documents list show ingested :Knowledge records and counts.
- [ ] Full upload → ingest → visible in both views.
- [ ] Builds clean (backend + frontend).
- [ ] Human review before observability work.

- [ ] Task 5: Ensure Ingest→Documents refresh + state

## Phase 2: Context Propagation + Auto-Instrumentation
- [ ] Task 6: Extend logging.py with document context + convenience
- [ ] Task 7: Thread ids + emit events through ingest/workflow
- [ ] Task 8: Send x-correlation-id from frontend on all calls

### Checkpoint: After 6-8
- [ ] Traceable logs (ids present end-to-end) for ingest flow.
- [ ] Builds + manual trigger works.
- [ ] No perf hit (log is cheap).

## Phase 3: Log Page + :Log Records
- [ ] Task 9: :Log model + Neo4jClient create/list methods
- [ ] Task 10: Backend logs API + registration
- [ ] Task 11: Frontend logs proxy + api-client + types
- [ ] Task 12: LogsView component
- [ ] Task 13: Wire Logs into navigation + main shell

### Final Checkpoint + Polish
- [ ] All 6 spec success criteria met (see patch doc).
- [ ] One full cycle: upload → ingest (with logs) → view in Documents + Logs page → delete → clean + dashboard 0.
- [ ] Logs contain ids; :Log nodes present.
- [ ] Builds (full docker or npx + py_compile).
- [ ] This patch doc updated with shipped note.
- [ ] tasks/ reviewed.

**Status legend:** Use the checkboxes. Re-run verification on any change.

See tasks/plan.md for full description, files, AC, verification per task.
**Dependencies and order must be respected.**
