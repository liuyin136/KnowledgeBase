/**
 * Exception hierarchy + error response helper.
 * Mirrors core/exceptions.py + error-handling-retry-strategy_v1.1.md §1, §2.
 *
 * Every non-2xx API response uses the standardized shape:
 *   { "error": { "code": string, "message": string, "details"?: object } }
 */

import { NextResponse } from "next/server";
import { ERROR_CODES, type ErrorCode } from "./constants";
import type { ErrorBody } from "./types";

/** Base exception for all RAG platform errors. */
export class RAGError extends Error {
  code: ErrorCode = ERROR_CODES.INTERNAL_ERROR;
  status: number = 500;
  details?: Record<string, unknown>;

  constructor(message: string, details?: Record<string, unknown>) {
    super(message);
    this.name = this.constructor.name;
    this.details = details;
  }
}

export class ValidationError extends RAGError {
  code: ErrorCode = ERROR_CODES.VALIDATION_ERROR;
  status = 422;
}

export class NotFoundError extends RAGError {
  code: ErrorCode = ERROR_CODES.NOT_FOUND;
  status = 404;
}

export class IngestError extends RAGError {
  code: ErrorCode = ERROR_CODES.INGEST_FAILED;
  status = 500;
}

export class EmbeddingError extends RAGError {
  code: ErrorCode = ERROR_CODES.EMBEDDING_FAILED;
  status = 502;
}

export class DBError extends RAGError {
  code: ErrorCode = ERROR_CODES.DB_ERROR;
  status = 500;
}

export class SearchError extends RAGError {
  code: ErrorCode = ERROR_CODES.SEARCH_FAILED;
  status = 500;
}

export class RerankError extends RAGError {
  code: ErrorCode = ERROR_CODES.RERANK_FAILED;
  status = 502;
}

/** Convert any thrown value into the standard error body. */
export function toErrorBody(err: unknown): { body: ErrorBody; status: number } {
  if (err instanceof RAGError) {
    return {
      status: err.status,
      body: {
        error: {
          code: err.code,
          message: err.message,
          ...(err.details ? { details: err.details } : {}),
        },
      },
    };
  }
  // Unknown error — never leak internal stack traces (error-handling spec §2).
  const message = err instanceof Error ? err.message : "Unexpected error";
  return {
    status: 500,
    body: {
      error: {
        code: ERROR_CODES.INTERNAL_ERROR,
        message,
      },
    },
  };
}

/** Build a NextResponse with the standardized error body. */
export function errorResponse(err: unknown): NextResponse {
  const { body, status } = toErrorBody(err);
  return NextResponse.json(body, { status });
}

/** Structured logging helper with experiment_id / stage / error_code (error-handling spec §4). */
export function logPipelineError(params: {
  experimentId?: string | null;
  stage: "chunking" | "embedding" | "db_write" | "retrieval" | "rerank" | "persist" | "orchestrator";
  err: unknown;
  retryCount?: number;
}) {
  const { experimentId, stage, err, retryCount } = params;
  const code = err instanceof RAGError ? err.code : ERROR_CODES.INTERNAL_ERROR;
  const message = err instanceof Error ? err.message : String(err);
  console.error(
    JSON.stringify({
      event: "pipeline.error",
      experiment_id: experimentId ?? null,
      stage,
      error_code: code,
      error_message: message,
      retry_count: retryCount ?? 0,
      timestamp: new Date().toISOString(),
    }),
  );
}

export function logPipelineEvent(params: {
  event: string;
  experimentId?: string | null;
  stage?: string;
  [k: string]: unknown;
}) {
  console.log(JSON.stringify({ timestamp: new Date().toISOString(), ...params }));
}
