# API & Interface Design v1.1 – Local-First RAG Experimentation Platform

**Version**: 1.1 (Cleaned & Consolidated)  
**Date**: 2026-07-04

This document defines the stable, hard-to-misuse REST API contract between frontend and backend for v1. It follows contract-first principles and is aligned with Backend Design Scope v1.1.

---

## 1. Design Principles

- Contract first
- Consistent error semantics (`{"error": {"code", "message", "details"}}`)
- Validate at boundaries only
- Prefer addition over modification
- Predictable naming (plural nouns, camelCase)
- Input/Output separation

---

## 2. Core Type Definitions (Single Source of Truth)

```ts
type ChunkMethod = 'Recursive' | 'Semantic' | 'Structure-Aware';
type EmbeddingApproach = 'LongText' | 'ChildChunk';
type AdvOption = 'None'; // v1 only

interface IngestConfig {
  embeddingApproach: EmbeddingApproach;
  chunkMethod: ChunkMethod;
  advOption?: AdvOption; // always "None" in v1
}

interface SearchConfig {
  hybridAlpha: number;      // 0.0 - 1.0
  useBm25: boolean;
  topKVector: number;
  topNRerank: number;
  useReranker: boolean;
  parentContextLevels?: number;
}

interface ChunkMetadata { /* ... */ }
interface Experiment { /* ... */ }
interface SearchResult { /* ... */ }
interface Memory { /* ... */ }
interface MemoryCart { /* ... */ }
```

---

## 3. REST API Specification (v1)

**Base**: `/api/v1`

### Experiments & Observability
- `POST /experiments` → create
- `GET /experiments` (paginated)
- `GET /experiments/{id}`
- `GET /experiments/{id}/chunks` (observability)

### Documents
- `POST /documents` (multipart)
- `GET /documents` (paginated)
- `DELETE /documents/{id}`

### Ingest (Unified – Recommended)
- `POST /ingest`
  Body: `{ documentId, config: IngestConfig, experimentDescription? }`
  → `202 { jobId, experimentId, status }`

Progress via polling `GET /ingest/{jobId}/status` or SSE.

### Search
- `POST /search`
  Body: `{ rawQuery, config: SearchConfig, experimentId? }`
  → `{ searchId, results: SearchResult[], metadata }`

- `GET /searches/history` (paginated)

### Memory & Memory Cart
- `POST /memories`
- `POST /memory-carts`
- `GET /memory-carts`
- `PATCH /memory-carts/{id}` (update selection)

---

## 4. Error Contract

Every non-2xx response:
```json
{
  "error": {
    "code": "VALIDATION_ERROR" | "NOT_FOUND" | "INGEST_FAILED" | ...,
    "message": "...",
    "details": {}
  }
}
```

---

## 5. Observability & Long-Running Jobs

Long-running operations (ingest, search) return `202` + `jobId`.  
Progress events include per-chunk `ChunkMetadata` for real-time frontend display.

---

## 6. Frontend Integration Notes

The API is designed to directly support the four core workflows + Experiments page with rich metadata for systematic testing and comparison.

**End of API & Interface Design v1.1**