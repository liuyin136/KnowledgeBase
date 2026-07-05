"""
api/v1/documents.py — Document upload + list + delete endpoints.

  • POST   /api/v1/documents    — JSON {filename, text, contentType?} OR multipart file
  • GET    /api/v1/documents    — list (paginated)
  • DELETE /api/v1/documents/{id} — delete by source_file

Documents are stored in Neo4j as :Knowledge nodes (one per ingest run, or one
per LongText sliding window). The `/documents` endpoint serves a logical
"unique source files" view derived from the Knowledge graph.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.dependencies import get_db
from app.core.exceptions import NotFoundError, ValidationError
from app.db.neo4j_client import Neo4jClient
from app.models.neo4j_models import Knowledge
from app.schemas.common import Paginated
from app.schemas.document import CreateDocumentRequest, DocumentCreatedResponse, DocumentItem

router = APIRouter(prefix="/documents", tags=["documents"])


def _knowledge_to_document(k_row: dict) -> DocumentItem:
    """Coerce a list_documents() row into a DocumentItem."""
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
    )


def _create_document_impl(
    *,
    filename: str,
    text: str,
    content_type: Optional[str],
    db: Neo4jClient,
) -> DocumentCreatedResponse:
    """Persist an upload-time :Knowledge placeholder node carrying the document text.

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
        experiment_id="upload",  # pseudo-experiment id for uploaded-but-not-ingested docs
        vector=None,  # null vector → excluded from HNSW index
        text=text,
        chunk_index=0,
        char_start=0,
        char_end=len(text),
    )
    db.create_knowledge(knowledge)
    return DocumentCreatedResponse(id=source_file)


@router.post("", response_model=DocumentCreatedResponse, status_code=201)
async def create_document(
    body: Optional[CreateDocumentRequest] = None,
    file: Optional[UploadFile] = File(default=None),
    filename: Optional[str] = Form(default=None),
    contentType: Optional[str] = Form(default=None),
    db: Neo4jClient = Depends(get_db),
) -> DocumentCreatedResponse:
    """Create a document from JSON body OR multipart form.

    JSON body:  {filename, text, contentType?}
    Multipart:  file=<upload>, filename=<optional>, contentType=<optional>
    """
    if file is not None:
        # Multipart path
        raw = await file.read()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationError(
                f"File is not valid UTF-8: {exc}",
                details={"filename": file.filename},
            ) from exc
        fname = filename or file.filename or "uploaded.txt"
        ctype = contentType or file.content_type or "text/plain"
        return _create_document_impl(filename=fname, text=text, content_type=ctype, db=db)

    if body is None:
        raise ValidationError(
            "Request must include a JSON body or a multipart file upload",
        )
    return _create_document_impl(
        filename=body.filename,
        text=body.text,
        content_type=body.contentType,
        db=db,
    )


@router.get("", response_model=Paginated[DocumentItem])
def list_documents(
    page: int = 1,
    pageSize: int = 20,
    db: Neo4jClient = Depends(get_db),
) -> Paginated[DocumentItem]:
    items_raw, total = db.list_documents(page=page, page_size=pageSize)
    items = [_knowledge_to_document(r) for r in items_raw]
    return Paginated[DocumentItem](
        items=items,
        total=total,
        page=page,
        pageSize=pageSize,
        hasMore=(page * pageSize) < total,
    )


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
