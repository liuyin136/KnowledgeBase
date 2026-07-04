# Task 5-c — Memory Cart + Experiments views

**Agent**: full-stack-developer (Memory Cart + Experiments views)
**Task ID**: 5-c
**Files touched (only these two)**:
- `src/components/rag/views/memory-view.tsx` (overwrote stub)
- `src/components/rag/views/experiments-view.tsx` (overwrote stub)

## What was built

### MemoryView (`memory-view.tsx`)
Two-column layout (`lg:grid-cols-[340px_minmax(0,1fr)]`):
- **Left column**
  - `CreateCartCard` — name Input + optional description Textarea + "Create Cart" button. Calls `api.memoryCarts.create`, toasts success, invalidates `["carts"]`, clears form, auto-selects new cart id.
  - `CartsList` — `useQuery(["carts"])` over `api.memoryCarts.list`. Each cart is a clickable Card-like row with name, description (line-clamp-2), memoryCount badge, relative updatedAt. Selected cart gets `ring-2 ring-primary border-primary bg-accent/40 shadow-sm`; hover adds `shadow-sm` + teal-tinted border. Empty state: "No carts yet. Create one to start curating retrieval results."
- **Right column**
  - `CartDetailPlaceholder` when no cart selected.
  - `CartDetail` — `useQuery(["cart", cartId])`. Header shows name (with edit affordance), description, memory count, created/updated relative times, refresh button. `CardAction` hosts the "Add memories" button.
  - `EditCartDialog` — Dialog with name + description fields → `api.memoryCarts.patch(id, {name, description})`. Invalidates `["cart", id]` + `["carts"]`.
  - `AddMemoriesDialog` — Dialog loading all recent memories (`api.memories.list({page:1,pageSize:100})`), filters out memories already in cart, search box for query text, multi-select with checkboxes → `api.memoryCarts.patch(id, {addMemoryIds})`. Invalidates `["cart", id]` + `["carts"]`.
  - `MemorySelectionTable` — Table with checkbox column (checked = in cart) + query (line-clamp-2) + chunk text (line-clamp-2) + score + vectorScore + bm25Score + rerankerScore + createdAt. Unchecking a row triggers optimistic mutation: `api.memoryCarts.patch(id, {memoryIds: remaining})` with `onMutate` updating query cache, `onError` rolling back, `onSuccess` toasting "Updated selection (N memories)". Each row click opens `MemoryDetailSheet` showing full queryText, full chunkText, all scores (final/vector/bm25/fused/reranker/success), notes, createdAt. Container is `max-h-[60vh] overflow-y-auto thin-scroll`; score cells are `font-mono text-xs`.
  - `AllMemoriesSection` — Collapsible card showing `api.memories.list({page:1,pageSize:50, experimentId?})` with a `Select` filter of search experiments (`api.experiments.list({kind:"search"})`). Read-only table; clicking a row opens the same `MemoryDetailSheet`.

### ExperimentsView (`experiments-view.tsx`)
Three local modes: `list | detail | compare` (state via `useState`).
- **Auto-open**: on mount, if `useUIStore.activeExperimentId` is set, switches to detail mode for it. The back button clears `activeExperimentId` and returns to list.
- **List mode**
  - `ViewHeader` with title "Experiments", description "History, metadata & comparison", icon `FlaskConical`. Actions: `ToggleGroup` (All / Ingest / Search) bound to `kind` filter.
  - `ExperimentTable` — paginated table (page size 15) with columns: checkbox (max 2 selectable, disabled beyond), Description (truncated + id), Approach badge, Chunk method badge, # Chunks (mono), Avg tokens (mono), Total time (formatted ms/s), Status badge (color-coded: completed=teal, failed=destructive, running=amber, pending=slate), Source file (truncated), Created (relative). Row click → detail mode. `hover:bg-muted/50`. Prev/Next pagination.
  - Sticky "Compare selected (2 experiments) →" button appears when 2 are checked → `setMode("compare")`.
  - Empty state: "No experiments yet. Start an ingest or run a search."
- **Detail mode**
  - Back button "← Back to list".
  - `api.experiments.get(id)` + `api.experiments.chunks(id)`.
  - Title card with description + id + created/updated. If `status === "failed"`: destructive `Alert` with errorCode + errorMessage.
  - `ObservabilityPanel` — stat-cards grid: totalChunks, avgTokensPerChunk, totalTimeMs, status, embeddingApproach, chunkMethod, advOption, sourceFile, Σ chunking ms, Σ embedding ms. For search experiments also: hybridAlpha (with auto-tune hint), useBm25, useReranker, topKVector, topNRerank, parentContextLevels, bestAlpha (when auto-tuned), rawQuery.
  - `ChunkBrowser` — `max-h-96 overflow-y-auto thin-scroll` table of chunks with columns # / Method / Embedding / Tokens / Chunk ms / Embed ms / Section / Preview. Row click → `ChunkInspectorSheet` (right-side Sheet) showing full text + all metadata + parentSourceFile.
  - "Compare with…" button opens `ComparePickerDialog` (Dialog + Select of all other experiments) → switches to compare mode with both ids.
- **Compare mode**
  - Back button. Two experiments side-by-side (`lg:grid-cols-2`), each renders its own `ObservabilityPanel` with `label` A/B.
  - `ComparisonTable` — rows: embeddingApproach, chunkMethod, totalChunks, avgTokensPerChunk, totalTimeMs, Σ chunking time, Σ embedding time, status, sourceFile. Columns: Metric | Experiment A | Experiment B | Δ (B−A). Δ shown in teal for `+`, muted-foreground for `−`, `—` when not applicable.
  - `BarComparison` — lightweight div-based bars comparing chunk count + avg tokens/chunk side-by-side (A vs B).
  - Footer note: "Comparison helps you see how changing one factor (embedding approach OR chunk method) affects retrieval metadata."

## Helpers / shared
- `relativeTime` (date-fns `formatDistanceToNow`), `fmtMs`, `fmtScore`, `fmtNum`, `truncate`/`line-clamp`.
- `statusBadge`, `approachBadge`, `chunkMethodBadge` for consistent color-coding.
- All numeric values use `font-mono text-xs`.

## Quality
- Both files start with `"use client"`.
- TypeScript strict; no `any` in app code (only inherited from the `api` client).
- TanStack Query for all server state. Mutations (`createCart`, `patchCart`, `toggleMemory`) invalidate `["carts"]` / `["cart", id]`.
- Loading skeletons, error states, empty states throughout.
- Accessible: `aria-label`s on icon buttons, `aria-current` on selected cart, focus-visible rings, keyboard-toggleable checkboxes/dialogs/sheets.
- Responsive: mobile stacks (single column), lg breaks to 2-col for memory; experiments list/detail/compare adapt naturally.
- Lint: `bun run lint` passes with 0 errors, 0 warnings.
- Dev server (`tail dev.log`) shows clean compiles + `GET / 200` after edits.

## Notes for downstream agents
- The `ChunkMetadata` type from `@/lib/rag/types` does NOT include `text` or `parentSourceFile`, but the chunks endpoint returns both. I declared a local `ChunkRow extends ChunkMetadata` with those two extra fields in `experiments-view.tsx`. If you need the same shape elsewhere, replicate or hoist this extension.
- The `Experiment` interface in `experiments-view.tsx` is a hand-written superset of the API contract; it includes the optional search-specific fields (`hybridAlpha`, `useBm25`, `useReranker`, `topKVector`, `topNRerank`, `parentContextLevels`, `autoTuneWeights`, `bestAlpha`, `rawQuery`) which Prisma returns but the v1.1 contract doc lists as optional.
- Optimistic selection toggle lives in `MemorySelectionTable.toggleMut` — it `getQueryData`/`setQueryData` on `["cart", cartId]` and rolls back on error.
