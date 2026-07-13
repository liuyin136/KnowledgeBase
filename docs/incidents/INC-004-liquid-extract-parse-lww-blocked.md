# INC-004 — Liquid extract parse failure blocks LWW re-extract (version stuck at 1)

## Status

closed

## Date

2026-07-12

## Symptom

CP-2-E2E Flow 2 (same query + same grandchild selection saved twice) fails: `extract_memory_graph` RQ job errors; `:Memory.version` stays at 1. User log in `data/Debug/2026-07-12_debug_log_phase2`.

## Root cause

Job failed in `liquid_extract` **before** `merge_memory_graph` — LWW logic never ran.

1. **YAML parse:** Liquid returned claim text with unquoted colons (e.g. `(.cursor/rules/docker-build.mdc):`). `yaml.safe_load` raised `mapping values are not allowed here`.
2. **JSON truncation (post partial fix):** After switching to JSON-first, `max_tokens=1024` truncated LLM output mid-string (`"summary": "Phase 2 will` → unexpected end of stream).

## Fix

`backend/app/services/liquid_extract.py`:

- JSON-first prompt and parse chain (`json.loads` → brace extract → YAML fallback)
- `max_tokens` 1024 → 2048
- Shorter chunk text in prompts (800 / 400 on compact retry)
- Compact-prompt retry on parse failure

Verified in `data/Debug/debug-83968f.log`: `prior_version: 1` → `merge_ok` with `version: 2`.

**Note:** Incident drafted manually from `.cursor/debug-pending.json` — Cursor Debug Mode stop hook did not promote `INC-DRAFT-*` automatically.

## Files touched

- `backend/app/services/liquid_extract.py`
- `tests/test_liquid_extract_parser.py`
- `docs/pitfalls/TRAPS-PHASE-2.md`

## Regression

```bash
docker exec -e IN_WORKER_EXEC=1 raglab-api-worker python -m pytest \
  tests/test_liquid_extract_parser.py tests/test_memory_extract.py -q
```

## ADR candidate

- [ ] Yes
- [x] No — parser/output contract fix; no schema or purge policy change

## Related

- Trap: [TRAPS-PHASE-2.md](../pitfalls/TRAPS-PHASE-2.md) (Liquid YAML colons + truncation)
- Phase: 2.0 GraphRAG + Memory — CP-2-E2E Flow 2 (G2)
