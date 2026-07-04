# Frontend Workflow Mapping & Component Architecture v1.1

**Aligned with**: Backend Design Scope v1.1 + API Interface Design v1.1

---

## 1. Core Workflows (v1)

The platform supports four core workflows for systematic experimentation:

1. **Ingest** (Document upload + embedding/chunking with full observability)
2. **Hybrid Search** (Tunable retrieval with parent-child awareness)
3. **Memory Cart** (Researcher curation of retrieval results)
4. **Experiments** (History, metadata, comparison — first-class for learnability)

Structured Chat is deferred to v2.

---

## 2. Recommended Frontend Structure (Next.js 15 + shadcn/ui)

**Tech Stack**:
- Next.js 15 App Router + TypeScript
- Tailwind + shadcn/ui (clean neutral colors + teal accent, dark mode support)
- TanStack Query v5
- Zustand (light client state)
- react-hook-form + zod

**Main Navigation (Sidebar)**
- Dashboard
- Ingest
- Hybrid Search
- Memory Cart
- Experiments

---

## 3. Page & Component Mapping

### Ingest Page
- Document upload / selector
- Config form (`IngestConfig`: embeddingApproach, chunkMethod)
- "Start Ingestion" button
- Live progress panel with per-chunk `ChunkMetadata` table (tokens, time, method)
- Chunk inspector drawer
- On completion → link to Experiment detail

**Key Components**: `IngestConfigForm`, `IngestProgress`, `ChunkInspector`

### Hybrid Search Page
- Query input + `SearchConfig` controls (hybrid alpha slider, BM25 toggle, reranker toggle, top-k)
- Results list with scores, parent context, metadata badges
- Multi-select + "Add to Memory Cart"
- Past searches history (re-run / continue)

**Key Components**: `SearchConfigPanel`, `SearchResultsList`, `ResultCard`

### Memory Cart Page
- List of carts
- Detail view with checkbox selection of memories/chunks
- Save / edit cart

**Key Components**: `MemoryCartList`, `MemorySelectionTable`

### Experiments Page (Critical for v1 learnability)
- Table of past experiments (ID, date, description, embedding approach, chunk method, #chunks, total time)
- Click → detail view with full stats + chunk browser + observability data
- Basic side-by-side comparison of two experiments

**Key Components**: `ExperimentTable`, `ExperimentDetail`, `ObservabilityPanel`

### Dashboard
- Quick start cards for the 4 workflows
- Recent experiments
- System health (models loaded, Neo4j, GPU)

---

## 4. Observability Display (Non-Negotiable)

Every Ingest and Search result must clearly surface:
- Embedding approach + exact model
- Chunking method + parameters
- Per-chunk token count and processing time
- Parent-child relationships
- Retrieval scores and config used (`hybrid_alpha`, reranker on/off)

This enables the researcher to understand exactly what combination is being tested.

---

## 5. State & Data Flow

- Server state via TanStack Query (experiments, documents, search results, memory carts)
- Client state (selected chunks for Memory Cart, current filters) via Zustand
- Long-running progress via SSE or polling + optimistic updates where appropriate

---

**End of Frontend Workflow Mapping v1.1**

This mapping ensures the frontend directly supports systematic experimentation and rich observability as required by the Project Directive.