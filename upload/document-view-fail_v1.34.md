# Document View Failure (v1.34 Investigation) — Mission Failure: Cannot See :Knowledge / :KnowledgeChunk in Experiments Page

**Date:** 2026-07-05  
**Workspace:** D:\KnowledgeBase2 (branch v1.3-replace)  
**Status:** Persistent unfixed after multiple debug/implementation cycles.  
**File created per user request** using /documentation-and-adrs skill to record the failure.

## User Symptoms (recap, across iterations)
- In **Experiments page** (detail view for ingest experiments):
  - Cannot see the **raw uploaded file** stored as :knowledge (pre-ingest Upload node with embedding_method='Upload', text, source_file).
  - Cannot see the **ingested chunk** from :knowledgechunk (or the parent :Knowledge full document text) tied to the experiment.
- List view only shows `sourceFile` filename (metadata only).
- Detail "Source Document" cards, ChunkBrowser, and reconstruction show empty states ("No chunks recorded", "No raw text found"), previews only, or nothing.
- Related: In Ingest page, hard to see own LongText :knowledge (lumped in documents list without distinction).
- Questions from user:
  1. Can I browse/modify (raw/rendered) the original :knowledge?
  2. Can I re-do ingest actions from Experiments page?
  3. Can I trigger childchunk ingestion on ingested docs from here?
  4. Why can't I see longtext knowledgechunk in ingest page?

## Environment / History Snapshot
- Full stack: Next.js frontend, FastAPI backend, Neo4j (labels: Experiment, Knowledge, KnowledgeChunk), Redis.
- Key data model (from neo4j-schema, models, orchestrator):
  - Upload: `CREATE (k:Knowledge {source_file, text, embedding_method: 'Upload', experiment_id: 'upload', ...})`
  - Ingest (LongText/ChildChunk): Creates new `Knowledge` (with `experiment_id`, full `text` for parent) + `KnowledgeChunk` (children) linked via HAS_CHUNK. Experiment node has `source_file`.
- Previous attempts (from chat history, plan.md, code):
  - Enhanced `list_chunks_for_experiment` (MATCH Knowledge {experiment_id} + HAS_CHUNK; return parents + children with `node_type`, full `text` via dict()).
  - `_chunk_to_response` passes full `text` + `nodeType` to ChunkMetadata (beyond preview).
  - Added `get_experiment_document` + `GET /experiments/{id}/document` (backend retrieves original via get_original_knowledge + ingested via chunks).
  - Frontend: api.experiments.document, OriginalDocumentSection (tries to use documentData or fetch, prefer ingested.text), ChunkBrowser (nodeType badges, longer snippets for knowledge), SourceDocumentSection (reconstruct prefers knowledge text), re-ordering, badges in ingest list.
  - Other: Hardened delete (only Uploads), defensive list_experiments (coalesce), lifted data in DetailMode.
  - Test script: test_experiment_neo4j_content_retrieval.py (simulates queries for text lengths by experiment_id).
  - Plan iterations, using-agent-skills, debugging-and-error-recovery applied repeatedly.

Despite this, "Problem unfixed. Mission failure."

## Investigation / Root Cause Analysis (using debugging-and-error-recovery + using-agent-skills)
Followed skills:
- **using-agent-skills**: Task = "fix visibility of :knowledge/:knowledgechunk in Experiments". Phase = "Something broke" → primary skill debugging-and-error-recovery. Multiple skills applied (documentation-and-adrs for this record, incremental-implementation for attempts).
- **debugging-and-error-recovery triage**:
  1. Reproduce: Upload .md → ingest (LongText/ChildChunk) → Experiments list/detail → no full document content visible (only filename or empty).
  2. Localize: 
     - List: pure Experiment metadata (source_file only; see experiments.py list_experiments + neo4j_client).
     - Content paths: chunks (experiment_id on Knowledge) or /documents/{source}/text (Upload filter). New /document endpoint added.
     - UI: Original/Source/ChunkBrowser should render full .text from responses.
  3. Reduce to minimal failing case:
     - Backend responses *do* contain text (verified in creation: orchestrator sets text + experiment_id; list_chunks returns via dict(p); get_experiment_document combines).
     - But frontend fails to display.
  4. Root cause: **Conditional hook violation in OriginalDocumentSection** (and related lift logic).
     - Code: `if (!documentData && experimentId) { const docQ = useQuery(...) }` — hooks called conditionally (only when no pre-fetched data).
     - React Rules of Hooks: Hooks must be called at the top level on every render, unconditionally. Violating this causes:
       - "Invalid hook call" errors (or silent failures in prod).
       - Stale closures, missed updates, no re-render when data arrives.
       - The "documentData" lift in DetailMode + conditional in child = race conditions / broken state.
     - Secondary: 
       - Over-complex fallback logic (documentData vs. own fetch) led to duplication and errors.
       - ChunkBrowser table still preview-heavy (full text only in inspector/sheet).
       - Source reconstruction prefers chunks but UI breakage prevents "first" visibility.
       - No end-to-end test of the full flow (backend retrieve → /api → frontend render) in real data.
       - Past "fixes" (UI sections, reordering) treated symptoms without fixing data flow/render.
  5. Fix root (not symptoms): Always top-level hooks, use pre-fetched or consistent fetch, prioritize full .text display for :knowledge (card first), label :knowledgechunk clearly, verify with script + real ingest.
- Evidence from code inspection (no live run possible without full env/DB):
  - Chunks response: items have `text` (full for parents), `nodeType`.
  - But conditional useQuery breaks consumption.
  - Similar patterns in other views avoided this.
- Logs: Neo4j notifications (missing props on Experiment) — side issue, not the visibility blocker.

## Consequences of Failure
- User cannot browse raw/rendered :knowledge or experiment's :knowledgechunk.
- Cannot reliably do re-ingest/childchunk from Experiments (Q2/Q3 blocked by lack of visibility).
- Longtext knowledgechunk invisible in ingest (Q4).
- Wasted cycles on UI patches without backend-frontend data contract verification.
- Risk of similar failures in other views (memory, search) that rely on chunks/knowledge.
- Documentation debt: No prior ADR for the Experiment/Knowledge linking model (denormalized experiment_id vs. relations).

## Alternatives Considered (during attempts)
- Always fetch in children (avoids conditional but duplicates queries).
- Lift *everything* to DetailMode + props only (better, but hooks still conditional in child code).
- Change data model (add :Experiment -[:HAS_DOCUMENT]-> :Knowledge relation) — more correct but schema migration.
- Embed full text in Experiment node (simple for view but denormalizes, bloats metadata).

## What Should Have Been Done (lessons)
- Backend-first: Verify `get_experiment_document` + /document + chunks return full `text` + correct linking *before* UI.
- Test on /api (curl the endpoints with real ingest data).
- Then frontend: Use the data, but obey hooks rules strictly. Prioritize full text display.
- Always call hooks unconditionally (use `enabled` + early returns *after* hooks).
- Add e2e verification in test script (query neo4j, hit /api, assert UI structure).
- ADR for "How Experiments surface :Knowledge/:KnowledgeChunk content".
- Non-destructive: Edits create new; deletes preserve exp-linked records (already partially done).

## Timeline of Attempts (summarized from chat/plan)
- Initial: list_chunks only returned children (biased CASE).
- Enhanced chunks + nodeType + full text in responses.
- Added /document backend + frontend sections + lift.
- Re-design: backend retrieve first, then /api, then frontend (this cycle).
- Each time: "still can't see", "unfixed".

## Verification Steps (for future)
- Upload .md → Ingest (LongText + ChildChunk) → Experiments detail:
  - Original/Source card: full text (not empty/preview).
  - ChunkBrowser: knowledge rows (full doc) + knowledgechunk rows visible with text.
- curl /api/v1/experiments/{id}/document → has "ingested"."text" + "original".
- Test script run → non-zero text lengths for experiment_id-linked Knowledge.
- No React hook errors in console.
- Delete doc → exp still shows its knowledge (preserved).

## Recommendations
- Fix the conditional hook immediately (make fetch unconditional or remove conditional branch).
- Run full verification with real data/DB.
- Write ADR for the visibility design.
- Add automated test for the document flow.
- Consider explicit relations in Neo4j for robustness.

**This document records the failure so future work (or agents) avoids repeating the same anti-patterns and incomplete integrations.**

(Generated following documentation-and-adrs skill: captured *why* the visibility failed, context, alternatives, consequences. Not just "the code".)