# Architecture Decision Records

| ADR | Title | Status |
|-----|-------|--------|
| [ADR-001](ADR-001-neo4j-v162-ingestion-graph.md) | Neo4j v1.62 ingestion graph | Accepted |
| [ADR-002](ADR-002-vault-neo4j-purge-api.md) | Vault Neo4j purge API selection | Accepted |
| [ADR-003](ADR-003-vault-index-status-lifecycle.md) | Vault index status lifecycle (1.7) | Accepted |
| [ADR-004](ADR-004-jina-rerank-n-batch-alignment.md) | Jina reranker n_batch / n_ctx alignment | Accepted |

**Auto-draft:** DEBUG stop hook writes `ADR-NNN-*.md` (status Draft) when `debug-pending.json` has `adr_candidate: true`. Review and set Status to Accepted.

**Traps:** BUILD-step lessons live in [docs/pitfalls/](../pitfalls/). Promote trap → ADR when invariant; do not duplicate ADR content as traps.

Registry: [_registry.json](_registry.json) ??next free number for hook allocation.


