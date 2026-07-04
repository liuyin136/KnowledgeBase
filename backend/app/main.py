"""
app/main.py — FastAPI application factory + lifespan + global exception handler.

Lifespan:
  1. Configure JSON logging.
  2. Initialize the Neo4j driver singleton + verify connectivity.
  3. Ensure vector indexes / constraints / fulltext indexes exist (idempotent).
  4. Initialize the Redis-backed ProgressTracker (falls back to in-memory).
  5. Preload the BGE-M3 embedding model (singleton) so the first request
     doesn't pay the load cost. Failure here is logged but non-fatal — the
     first /ingest or /search will retry the load.
  6. Build the PipelineOrchestrator singleton.

Global exception handler (per error-handling-retry-strategy_v1.1.md §2):
  • RAGBaseException → use its code/status_code/details.
  • FastAPI RequestValidationError → 422 VALIDATION_ERROR.
  • FastAPI HTTPException → preserve status, wrap body in {error:{...}}.
  • Any other Exception → 500 INTERNAL_ERROR (full traceback logged, NOT leaked).

CORS:
  • Allowed origins from settings.cors_origins (default ["*"] for dev).
  • Methods: all. Headers: all. Credentials: false (front-end uses Bearer/IPA).

Run:
  uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import traceback
from contextlib import asynccontextmanager
from typing import Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import RAGBaseException
from app.core.logging import (
    bind_correlation_id,
    configure_logging,
    get_logger,
    reset_correlation_id,
)
from app.db.neo4j_client import close_neo4j_client, get_neo4j_client
from app.db.vector_index import ensure_vector_indexes
from app.services.embedding import get_embedder
from app.workers.progress import get_progress_tracker

logger = get_logger("rag.main")


# ─── Lifespan ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup + shutdown lifecycle."""
    # ─── startup ────────────────────────────────────────────────────────────
    configure_logging(settings.log_level)
    logger.info(
        "lifespan.startup",
        extra={
            "event": "lifespan.startup",
            "neo4j_uri": settings.neo4j_uri,
            "redis_url": settings.redis_url,
            "model_path": settings.model_path,
            "device": settings.device,
            "embedding_dim": settings.embedding_dim,
        },
    )

    # Neo4j driver + schema
    try:
        neo4j = get_neo4j_client()
        neo4j.verify_connectivity()
        logger.info("lifespan.neo4j.ok", extra={"event": "lifespan.neo4j.ok"})
        try:
            ensure_vector_indexes(neo4j.driver, database=settings.neo4j_database)
            logger.info("lifespan.neo4j.schema_ok", extra={"event": "lifespan.neo4j.schema_ok"})
        except Exception as exc:
            # Non-fatal — queries will fail later but the API will boot.
            logger.warning(
                "lifespan.neo4j.schema_failed",
                extra={"event": "lifespan.neo4j.schema_failed", "error": str(exc)},
            )
    except Exception as exc:
        logger.warning(
            "lifespan.neo4j.unavailable",
            extra={"event": "lifespan.neo4j.unavailable", "error": str(exc)},
        )

    # Redis progress tracker (falls back to in-memory on connect failure)
    try:
        get_progress_tracker()
    except Exception as exc:
        logger.warning(
            "lifespan.progress.init_failed",
            extra={"event": "lifespan.progress.init_failed", "error": str(exc)},
        )

    # Preload BGE-M3 (best-effort — non-fatal if it fails; first request retries)
    try:
        embedder = get_embedder()
        embedder.load()
        logger.info(
            "lifespan.embedder.ok",
            extra={"event": "lifespan.embedder.ok", "device": embedder.device},
        )
    except Exception as exc:
        logger.warning(
            "lifespan.embedder.load_failed",
            extra={"event": "lifespan.embedder.load_failed", "error": str(exc)},
        )

    logger.info("lifespan.ready", extra={"event": "lifespan.ready"})
    yield

    # ─── shutdown ───────────────────────────────────────────────────────────
    logger.info("lifespan.shutdown", extra={"event": "lifespan.shutdown"})
    close_neo4j_client()


# ─── App factory ──────────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    app = FastAPI(
        title="Local-First RAG Experimentation Platform v1.2 — Backend",
        description=(
            "FastAPI backend (Python 3.12) — Neo4j + Redis + BGE-M3 on GPU. "
            "This is the canonical RAG engine per the directive; the Next.js app "
            "proxies to it. Standard paths only (no Late/Agentic Chunking, no "
            "Structured Chat, no GraphRAG, no multi-user)."
        ),
        version="1.2.0",
        lifespan=lifespan,
    )

    # ─── CORS ──────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    # ─── Routes ────────────────────────────────────────────────────────────
    app.include_router(api_router)

    @app.get("/health", tags=["health"])
    async def health() -> dict:
        """Health check (used by the Next.js backend-health check + Docker HEALTHCHECK)."""
        return {"status": "ok"}

    # ─── Global exception handlers (per error-handling spec §2) ────────────

    @app.exception_handler(RAGBaseException)
    async def rag_exception_handler(request: Request, exc: RAGBaseException) -> JSONResponse:
        # Structured error logging with experiment_id / stage / retry_count
        logger.error(
            "pipeline.error",
            extra={
                "event": "pipeline.error",
                "stage": exc.stage or "unknown",
                "error_code": exc.code,
                "error_message": exc.message,
                "experiment_id": exc.experiment_id,
                "retry_count": exc.retry_count,
                "path": str(request.url.path),
                "method": request.method,
            },
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_error_body(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # FastAPI validation errors → 422 VALIDATION_ERROR (contract).
        logger.warning(
            "validation.error",
            extra={
                "event": "validation.error",
                "path": str(request.url.path),
                "method": request.method,
                "errors": exc.errors(),
            },
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": {"errors": _safe_validation_errors(exc.errors())},
                }
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        # Wrap FastAPI HTTPException in the standardized error contract.
        code_map = {
            400: "VALIDATION_ERROR",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            409: "CONFLICT",
            422: "VALIDATION_ERROR",
            429: "RATE_LIMITED",
            500: "INTERNAL_ERROR",
            502: "BAD_GATEWAY",
            503: "SERVICE_UNAVAILABLE",
            504: "GATEWAY_TIMEOUT",
        }
        code = code_map.get(exc.status_code, "INTERNAL_ERROR")
        message = str(exc.detail) if exc.detail is not None else "HTTP error"
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": code,
                    "message": message,
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Catch-all: log the FULL traceback server-side, return a generic 500
        # to the client (never leak stack traces).
        tb = traceback.format_exc()
        logger.error(
            "unhandled.error",
            extra={
                "event": "unhandled.error",
                "path": str(request.url.path),
                "method": request.method,
                "error": str(exc),
                "traceback": tb,
            },
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An internal error occurred. See server logs for details.",
                }
            },
        )

    # ─── per-request correlation id middleware ─────────────────────────────
    @app.middleware("http")
    async def correlation_middleware(
        request: Request, call_next: Callable[[Request], Awaitable]
    ):
        import uuid as _uuid

        corr = request.headers.get("x-correlation-id") or str(_uuid.uuid4())
        token = bind_correlation_id(corr)
        try:
            response = await call_next(request)
            response.headers["x-correlation-id"] = corr
            return response
        finally:
            reset_correlation_id(token)

    return app


def _safe_validation_errors(errors):
    """Make FastAPI validation errors JSON-serializable (they contain pydantic
    objects sometimes)."""
    import json

    try:
        return json.loads(json.dumps(errors, default=str))
    except Exception:
        return [{"msg": str(e.get("msg", ""))} for e in errors]


# Module-level app instance (uvicorn entrypoint: `uvicorn app.main:app`)
app = create_app()
