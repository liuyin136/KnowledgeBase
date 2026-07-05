# Error Handling & Retry Strategy Specification (v1)

**Goal**: Consistent, observable, and resilient error handling across all pipelines while keeping the system simple for a research tool.

## 1. Exception Hierarchy (in `core/exceptions.py`)

```python
class RAGBaseException(Exception):
    """Base exception for all RAG platform errors."""
    code: str = "RAG_ERROR"
    status_code: int = 500

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
```

## 2. Global Exception Handler (FastAPI)

In `main.py` or a middleware:

- Catch all `RAGBaseException` → return consistent `{"error": {"code": ..., "message": ..., "details": ...}}`
- Log with `experiment_id` / `correlation_id` when available.
- Never leak internal stack traces to clients in production.

## 3. Retry Strategy

### Embedding Calls (most failure-prone)
- **Library**: Use `tenacity` or `retry` decorator.
- **Policy**:
  - Max 3 attempts
  - Exponential backoff: 1s → 2s → 4s
  - Retry on: transient network errors, rate limits (if any local model server), CUDA OOM (with smaller batch)
  - Do **not** retry on validation errors or permanent model loading failures.

### Neo4j Writes
- Retry on transient connection / deadlock errors (max 2 attempts).
- Use Neo4j transaction functions with retry built-in where possible.

### Long-running Ingest / Search Jobs
- Jobs should be idempotent where possible.
- On failure, persist `Experiment.status = "failed"` + error message in Neo4j.
- Frontend can poll status and show the error.

## 4. Observability of Errors

Every error must be logged with:
```json
{
  "event": "pipeline.error",
  "experiment_id": "...",
  "stage": "embedding" | "chunking" | "neo4j_write" | "retrieval",
  "error_code": "EMBEDDING_FAILED",
  "error_message": "...",
  "retry_count": 2
}
```

This allows the researcher to diagnose failures quickly via the Experiments page.

## 5. Frontend Error Handling

- All API errors follow the same shape → single error handling component in frontend.
- For long-running jobs: show progress + last known error if job fails.