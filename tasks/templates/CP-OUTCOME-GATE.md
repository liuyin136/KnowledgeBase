# CP-[PHASE] — Outcome Gates Template

Copy for new phase exit checklists. Developer signs **Then** only. Agent flows go in appendix.

## Outcome Gates (developer signs)

| ID | Given | When | Then | [ ] |
|----|-------|------|------|-----|
| G1 | Stack up (`docker compose up -d`) | [action] | [observable result] | |
| G2 | | | | |
| G3 | | | | |

**Verify:**

```bash
# one pytest or curl command
```

## Sign-off

Mirror Outcome Gate IDs — check only when Then is true:

- [ ] G1
- [ ] G2
- [ ] G3

## Automated regression

```bash
docker compose exec -e IN_WORKER_EXEC=1 api-worker python -m pytest ... -q
```

---

## Appendix — Agent flows (optional)

Step-by-step UI/API flows for agent verification. **Not required for developer sign-off.**

### Flow 1 — [Title]

1. ...
- [ ] ...
