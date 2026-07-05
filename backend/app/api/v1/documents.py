"""
api/v1/documents.py — Document upload + list + delete endpoints.

  • POST   /api/v1/documents    — JSON {filename, text, contentType?} (single) OR
                                   multipart with repeated 'file' (multi .md supported)
  • GET    /api/v1/documents    — list (paginated)
  • DELETE /api/v1/documents/{id} — delete by source_file

Upload flow now primary supports multiple .md files via drag/drop or browse on Ingest page.
JSON path preserved for edit-save and internal callers.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, File, Form, Query, UploadFile

from app.api.dependencies import get_db
from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger, log_pipeline_event
from app.db.neo4j_client import Neo4jClient
from app.models.neo4j_models import Knowledge
from app.schemas.common import Paginated
from app.schemas.document import CreateDocumentRequest, DocumentCreatedResponse, DocumentItem

logger = get_logger("rag.api.documents")


router = APIRouter(prefix="/documents", tags=["documents"])


def _knowledge_to_document(k_row: dict) -> DocumentItem:
    """Coerce a list_documents() row into a DocumentItem.

    Extra fields (representativeEmbeddingMethod, kinds) are accepted by the
    loose DocumentItem in ingest-view and used for badges/labels so users
    can distinguish raw Upload vs LongText ingested entries.
    """
    created = k_row.get("createdAt")
    if hasattr(created, "isoformat"):
        created = created.isoformat()
    return DocumentItem(
        id=k_row.get("id", ""),
        filename=k_row.get("filename", ""),
        contentType=k_row.get("contentType", "text/plain"),
        sizeBytes=int(k_row.get("sizeBytes") or 0),
        totalChunks=int(k_row.get("totalChunks") or 0),
        createdAt=created or datetime.utcnow(),
        representativeEmbeddingMethod=k_row.get("representativeEmbeddingMethod"),
        kinds=k_row.get("kinds") or [],
    )


def _create_document_impl(
    *,
    filename: str,
    text: str,
    content_type: Optional[str],
    db: Neo4jClient,
) -> str:
    """Persist an upload-time :Knowledge placeholder node carrying the document text.

    Returns the source_file (used as id).

    This is the "Upload document" flow — it stores the raw text in Neo4j so the
    subsequent /ingest call can recover it via `get_document_text(source_file)`.

    Design notes:
      • `embedding_method="Upload"` marks this as a pre-ingest placeholder so
        `get_document_text` can filter to upload-time nodes only (avoids double-
        counting text from prior ingest runs).
      • `vector=None` — the HNSW index skips null-vector nodes, so upload-time
        placeholders do NOT pollute vector search results.
      • The orchestrator's /ingest will create SEPARATE :Knowledge nodes (with
        real embeddings + embedding_method="LongText") when it actually ingests.
    """
    if not filename or not text:
        raise ValidationError(
            "filename and text are required",
            details={"filename": bool(filename), "text_len": len(text)},
        )
    # Use the filename as the source_file identifier so /ingest can look it up.
    source_file = filename
    knowledge = Knowledge(
        id=str(uuid.uuid4()),
        source_file=source_file,
        total_tokens=max(1, len(text) // 4),  # heuristic — replaced at ingest time
        embedding_method="Upload",  # marker — distinct from real LongText/ChildChunk embeddings
        created_at=datetime.utcnow(),
        vector=None,  # null vector → excluded from HNSW index
        text=text,
        chunk_index=0,
        char_start=0,
        char_end=len(text),
    )
    db.create_knowledge(knowledge)
    return source_file


def _is_markdown_filename(name: Optional[str]) -> bool:
    if not name:
        return False
    n = name.lower()
    return n.endswith(".md") or n.endswith(".markdown")


@router.post("", response_model=DocumentCreatedResponse, status_code=201)
async def create_document(
    body: Optional[CreateDocumentRequest] = Body(default=None),
    files: List[UploadFile] = File(default_factory=list),
    file: Optional[UploadFile] = File(default=None),  # legacy single file support
    filename: Optional[str] = Form(default=None),
    contentType: Optional[str] = Form(default=None),
    db: Neo4jClient = Depends(get_db),
) -> DocumentCreatedResponse:
    """Create document(s).

    - JSON: single {filename, text, contentType?} — used by paste/edit-save.
    - Multipart: one or more 'file' fields (preferred for multi .md upload on Ingest).
      Optional legacy single 'file' + Form fields kept for compatibility.
    Only .md/.markdown files accepted on the multipart path.
    """
    created_ids: List[str] = []

    # Multipart / file path (new multi-file primary path + legacy single)
    all_files: List[UploadFile] = []
    if files:
        all_files.extend(files)
    if file is not None:
        all_files.append(file)

    if all_files:
        for f in all_files:
            raw = await f.read()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValidationError(
                    f"File is not valid UTF-8: {exc}",
                    details={"filename": f.filename},
                ) from exc

            fname = (filename or f.filename or "uploaded.md")
            if not _is_markdown_filename(fname):
                raise ValidationError(
                    "Only .md files are accepted",
                    details={"filename": fname},
                )
            ctype = contentType or f.content_type or "text/markdown"
            sid = _create_document_impl(filename=fname, text=text, content_type=ctype, db=db)
            created_ids.append(sid)

        return DocumentCreatedResponse(ids=created_ids)

    # JSON body path (kept for compatibility with edit-save etc.)
    if body is not None:
        sid = _create_document_impl(
            filename=body.filename,
            text=body.text,
            content_type=body.contentType,
            db=db,
        )
        return DocumentCreatedResponse(ids=[sid])

    raise ValidationError(
        "Request must include a JSON body or multipart file upload(s)",
    )


@router.get("", response_model=Paginated[DocumentItem])
def list_documents(
    page: int = 1,
    pageSize: int = 20,
    db: Neo4jClient = Depends(get_db),
) -> Paginated[DocumentItem]:
    items_raw, total = db.list_documents(page=page, page_size=pageSize)
    items = [_knowledge_to_document(r) for r in items_raw]
    resp = Paginated[DocumentItem](
        items=items,
        total=total,
        page=page,
        pageSize=pageSize,
        hasMore=(page * pageSize) < total,
    )
    # observation: ingest documents list flow end - records served to UI (from neo4j Knowledge)
    log_pipeline_event(logger, "documents.response", "documents list response", total=total, page=page, returned=len(items))
    return resp


@router.delete("/{document_id}")
def delete_document(
    document_id: str,
    db: Neo4jClient = Depends(get_db),
) -> dict:
    deleted = db.delete_document(document_id)
    if deleted == 0:
        raise NotFoundError(
            f"Document {document_id} not found",
            details={"document_id": document_id},
        )
    return {"deleted": True, "count": deleted}


@router.get("/{document_id}/text")
def get_document_text(
    document_id: str,
    kind: Optional[str] = Query(default="upload", description="'upload' (raw pre-ingest) | 'any' (latest Knowledge for source)"),
    db: Neo4jClient = Depends(get_db),
) -> dict:
    """Return full text + metadata for a logical document (by source_file = document_id).

    - kind=upload: the original uploaded :Knowledge placeholder (what /ingest consumes).
    - kind=any: any Knowledge node for the source (may be a LongText parent from ingest).
    """
    if kind == "upload":
        k = db.get_original_knowledge(document_id)
        if not k:
            # fallback to old internal (may be empty if no Upload left)
            txt = db.get_document_text(document_id)
            return {"sourceFile": document_id, "text": txt, "kind": "upload", "embeddingMethod": "Upload"}
        return {
            "sourceFile": document_id,
            "text": k.get("text"),
            "kind": "upload",
            "embeddingMethod": k.get("embedding_method"),
            "createdAt": k.get("created_at"),
            "id": k.get("id"),
        }

    # kind any / latest: prefer a non-Upload Knowledge (ingested parent) if exists
    k = db.get_knowledge_by_source(document_id, prefer_non_upload=True)
    if not k:
        # last resort: old upload path
        txt = db.get_document_text(document_id)
        return {"sourceFile": document_id, "text": txt, "kind": "fallback", "embeddingMethod": "Upload"}
    return {
        "sourceFile": document_id,
        "text": k.get("text"),
        "kind": "knowledge",
        "embeddingMethod": k.get("embedding_method"),
        "experimentId": "",
        "createdAt": k.get("created_at"),
        "id": k.get("id"),
    }


@router.get("/{document_id}/chunks")
def get_document_chunks(
    document_id: str,
    db: Neo4jClient = Depends(get_db),
) -> dict:
    """Return chunks for a document by source_file (for Documents page, source_file based).
    Uses :Knowledge + :KnowledgeChunk directly.
    """
    chunks = db.list_chunks_for_source_file(document_id)
    # Build response shape (experimentId kept as "" for contract compatibility; no :Experiment)
    items = []
    for c in chunks:
        items.append({
            "chunkId": c.get("id"),
            "parentDocId": c.get("parent_doc_id") or c.get("id"),
            "experimentId": "",
            "chunkIndex": c.get("chunk_index"),
            "chunkMethod": c.get("chunk_method") or c.get("embedding_method"),
            "embeddingMethod": c.get("embedding_method"),
            "tokenCount": c.get("token_count"),
            "chunkingTimeMs": c.get("chunking_time_ms"),
            "embeddingTimeMs": c.get("embedding_time_ms"),
            "section": c.get("section"),
            "text": c.get("text"),
            "textPreview": c.get("text", "")[:220] if c.get("text") else "",
            "nodeType": c.get("node_type"),
            "parentSourceFile": c.get("source_file"),
        })
    return {"items": items, "total": len(items)}
