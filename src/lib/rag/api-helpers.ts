/**
 * Shared API helpers: pagination parsing + standardized error handling.
 */

import { NextRequest, NextResponse } from "next/server";
import { DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE } from "@/lib/rag/constants";
import { errorResponse, RAGError, ValidationError } from "@/lib/rag/errors";

/** Parse pagination params from a request URL. */
export function parsePagination(req: NextRequest): { page: number; pageSize: number } {
  const url = new URL(req.url);
  const page = Math.max(1, parseInt(url.searchParams.get("page") || "1", 10) || 1);
  const pageSize = Math.min(
    MAX_PAGE_SIZE,
    Math.max(1, parseInt(url.searchParams.get("pageSize") || String(DEFAULT_PAGE_SIZE), 10) || DEFAULT_PAGE_SIZE),
  );
  return { page, pageSize };
}

/** Wrap an async route handler with standardized error → errorResponse mapping. */
export function withErrors<T = unknown>(
  handler: () => Promise<NextResponse<T>>,
): Promise<NextResponse<T | unknown>> {
  return handler().catch((err) => errorResponse(err));
}

/** Parse JSON body; throw ValidationError on malformed JSON. */
export async function parseBody<T>(req: NextRequest): Promise<T> {
  try {
    return (await req.json()) as T;
  } catch {
    throw new ValidationError("Malformed JSON body");
  }
}

/** Standard 404 helper. */
export function notFound(message: string): NextResponse {
  return NextResponse.json(
    { error: { code: "NOT_FOUND", message } },
    { status: 404 },
  );
}

/** Re-export for convenience. */
export { errorResponse, RAGError };
