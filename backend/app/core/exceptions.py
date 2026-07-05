"""
core/exceptions.py — Custom exception hierarchy for the RAG platform.

Per error-handling-retry-strategy_v1.1.md §1:
  • RAGBaseException (code=RAG_ERROR, status=500) is the root.
  • Each subclass sets `code` (machine-readable) + `status_code` (HTTP).
  • All exceptions carry optional `details` for the standardized error body
    `{"error":{"code","message","details"?}}` emitted by the global handler
    in app/main.py.
  • Stack traces are NEVER leaked to the client; they are logged server-side
    with structured fields (experiment_id, stage, error_code, retry_count).

The global FastAPI exception handler in app/main.py catches:
  1. RAGBaseException → use its code/status_code/details.
  2. FastAPI RequestValidationError → 422 VALIDATION_ERROR.
  3. FastAPI HTTPException → preserve status, wrap body in error contract.
  4. Any other Exception → 500 INTERNAL_ERROR (logged with full traceback).
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class RAGBaseException(Exception):
    """Base exception for all RAG platform errors.

    Attributes:
        code: Machine-readable error code (e.g. "EMBEDDING_FAILED").
        status_code: HTTP status code to return.
        details: Optional structured details included in the error body.
        stage: Pipeline stage where the error occurred (for observability).
        experiment_id: Optional experiment id for correlation.
        retry_count: How many retries were attempted before giving up.
    """

    code: str = "RAG_ERROR"
    status_code: int = 500

    def __init__(
        self,
        message: str,
        *,
        details: Optional[Dict[str, Any]] = None,
        stage: Optional[str] = None,
        experiment_id: Optional[str] = None,
        retry_count: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.stage = stage
        self.experiment_id = experiment_id
        self.retry_count = retry_count

    def to_error_body(self) -> Dict[str, Any]:
        """Return the standardized `{"error": {...}}` body."""
        body: Dict[str, Any] = {
            "error": {
                "code": self.code,
                "message": self.message,
            }
        }
        if self.details:
            body["error"]["details"] = self.details
        return body


class ValidationError(RAGBaseException):
    code = "VALIDATION_ERROR"
    status_code = 422


class NotFoundError(RAGBaseException):
    code = "NOT_FOUND"
    status_code = 404


class IngestError(RAGBaseException):
    code = "INGEST_FAILED"
    status_code = 500


class EmbeddingError(RAGBaseException):
    code = "EMBEDDING_FAILED"
    status_code = 502


class Neo4jError(RAGBaseException):
    code = "NEO4J_ERROR"
    status_code = 500


class SearchError(RAGBaseException):
    code = "SEARCH_FAILED"
    status_code = 500


class RerankError(RAGBaseException):
    code = "RERANK_FAILED"
    status_code = 502


class JobNotFoundError(RAGBaseException):
    code = "JOB_NOT_FOUND"
    status_code = 404


class InternalError(RAGBaseException):
    code = "INTERNAL_ERROR"
    status_code = 500
