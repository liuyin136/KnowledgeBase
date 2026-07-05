# file-upload-issue_v1.32.md — Multipart Upload Proxy Bug (Ingest Page)

**Date**: 2026-07-05
**Status**: Fixed
**Related**: v1.3-replace branch, previous upload redesign work, `upload/frontend-cant-browser_v1.3*.md`, API_Interface_Design, Frontend_Workflow_Mapping

## Summary

After enabling real file uploads (multiple `.md` only) on the Ingest page, the feature worked in design but failed at runtime with frontend-to-backend communication errors (503 BACKEND_UNREACHABLE or the "Request must include a JSON body or a multipart file upload" validation error).

**Root cause**: The Next.js-to-FastAPI proxy (`proxyToBackend`) unconditionally consumed the request body with `await req.text()` *before* checking `content-type` and calling `await req.formData()`. This broke every multipart upload.

The problem only surfaced once the UI actually started sending `FormData` (the previous paste-only flow used JSON).

## Storage Location for Uploaded Content

**Uploaded files are NOT stored on disk or in any filesystem directory.**

They are persisted exclusively inside **Neo4j** as placeholder `:Knowledge` nodes:

- `source_file` = filename (used as the logical `documentId`)
- `text` = full original document content
- `embedding_method = "Upload"` (special marker)
- `vector = null` (deliberately excluded from the HNSW vector index)
- `experiment_id = "upload"` (pseudo-id to distinguish pre-ingest placeholders)
- `total_tokens` (heuristic), `chunk_index=0`, char range for the whole doc

See:
- `backend/app/api/v1/documents.py` → `_create_document_impl`
- `backend/app/db/neo4j_client.py` → `create_knowledge(...)` (raw Cypher CREATE)
- `get_document_text(source_file)` — **only** matches `embedding_method='Upload'` nodes
- `backend/app/models/neo4j_models.py` → `Knowledge` model

When "Start Ingestion" runs, the orchestrator reads the raw text from these nodes and creates *new* real `:Knowledge` (and `:KnowledgeChunk`) nodes with actual embeddings and different `embedding_method` values ("LongText" / "ChildChunk").

This design keeps upload-time data out of search results until explicitly ingested.

## Timeline of the Session

1. **Initial request** — Re-create the Upload Document mechanism:
   - Support multiple `.md` files only
   - Replace paste textarea primary UX with drag-and-drop + file input
   - Fix the long-standing "Request must include a JSON body or a multipart file upload" error

2. **Implementation** (following previous plan):
   - New `UploadDocumentCard` with native drag/drop, staging, batch FormData upload
   - `api.documents.upload(formData)` + FormData support in `request()`
   - Backend: `List[UploadFile]`, `Body(default=None)` for JSON path, `.md` validation
   - Response shape changed to `{ ids: string[] }`
   - Only Markdown accepted on the file path

3. **Bug discovery** (this session):
   - User reported "frontend to backend has issue" when uploading via the Ingest page.
   - "Inspect the ingest api to backend".
   - Reproduction: Use the new multi-file uploader on the Ingest view.

4. **Investigation** (using read/grep + proxy + handler tracing):
   - Traced: browser FormData → `/api/v1/documents` (Next) → `proxyToBackend` → FastAPI `/api/v1/documents`
   - Also looked at downstream `/api/v1/ingest` (start job) + status polling + `get_document_text`
   - Found the exact smoking gun in `src/lib/rag/backend-client.ts`:

     ```ts
     } else if (req.method !== "GET" && req.method !== "DELETE") {
       const text = await req.text();   // consumes body for ALL POSTs
       ...
     }
     if (req.method === "POST") {
       if (ct.includes("multipart/form-data")) {
         const form = await req.formData(); // too late — body already read
         ...
       }
     }
     ```

   - Consequence: multipart never reached the (now correctly written) backend handler.
   - Secondary: field name `"file"` vs backend `files: List[UploadFile]` (and legacy `file`).

5. **Fix**:
   - Reordered logic: inspect `content-type` first, branch on `isMultipart` *before* any body read.
   - Defensive handling for `opts.body instanceof FormData`.
   - Changed UI to `fd.append("files", f)` (plural) for correct List binding.
   - Added clear comments documenting the rule ("multipart body must be read via formData before any text()").
   - JSON paths for ingest start and edit-save were never affected and remain working.

## Root Cause Analysis

| Layer | What should happen | What was happening |
|-------|--------------------|--------------------|
| Browser | Send `multipart/form-data; boundary=...` with file parts | Correct |
| Next.js route | Forward request body untouched to proxy | Correct |
| `proxyToBackend` | Detect multipart → `formData()` → forward FormData object | `text()` first → stream consumed → `formData()` fails or empty |
| FastAPI | Bind `files: List[UploadFile]` or `file` | Received neither → fell through to validation error |
| UI | Receive 201 `{ids}` or useful error | Received 503 UNREACHABLE or the old validation message |

The proxy was written when only JSON paths existed. The multipart branch was aspirational ("Forward multipart untouched") but the execution order made it impossible.

## Decisions & Trade-offs

- **Decision**: Fix the proxy centrally rather than working around it in every route or the client.
  - Reason: All `/api/v1/*` traffic goes through this one function. Fixing it once benefits future multipart use cases (if any).
- **Decision**: Standardize on `"files"` plural in the FormData from the UI.
  - Kept backend tolerant of both `"file"` and `"files"`.
- **Decision**: Keep the error surface as 503 for now when proxy itself fails (existing contract), but the real errors from backend now flow through correctly.
- **Not changed**: Ingest job execution, Neo4j storage model, selection/ingest workflow, or any non-upload UI.

## Consequences

**Positive**:
- File upload on Ingest page now works end-to-end (multi `.md` → documents list → select → Start Ingestion → live progress).
- The ingest API (`POST /ingest` + status polling) can now be exercised after real uploads.
- Future multipart features have a working foundation.
- Documentation of a subtle but critical Next.js/FastAPI proxy gotcha.

**Risks / Gotchas** (documented in code):
- Never read the same `NextRequest` body twice (text + formData, or json + formData).
- Always check `content-type` before deciding how to consume the body.
- `FormData` objects must be passed through without `JSON.stringify`.

## Files Changed in This Session (summary)

- `src/lib/rag/backend-client.ts` — core proxy fix + comments
- `src/components/rag/views/ingest-view.tsx` — append key + comments
- Minor comment updates in routes

(Previous session changes: the multi-file UI, client `upload()`, backend `List[UploadFile]` + `Body()`, response shape, etc.)

## Verification Performed

- TypeScript (`tsc --noEmit`): clean (only unrelated example errors)
- ESLint on changed files: clean
- Python syntax on documents handler: OK
- Static tracing of both the document upload path and the subsequent `/ingest` start path
- Manual reproduction steps captured in the plan

## References

- `src/lib/rag/backend-client.ts` (proxyToBackend)
- `backend/app/api/v1/documents.py` (_create_document_impl, get paths)
- `backend/app/db/neo4j_client.py` (create_knowledge, get_document_text)
- Previous docs in `upload/`
- ADR-style thinking from documentation-and-adrs skill

---

**This document was produced following the documentation-and-adrs skill guidance** (capture the *why*, context, root cause, decisions, and consequences rather than just restating the diff).