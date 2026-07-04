/**
 * POST /api/v1/experiments → proxy to FastAPI backend.
 * GET  /api/v1/experiments → proxy (paginated, ?kind=ingest|search).
 */
import { NextRequest } from "next/server";
import { proxyToBackend } from "@/lib/rag/backend-client";
import { withErrors } from "@/lib/rag/api-helpers";

export async function POST(req: NextRequest) {
  return withErrors(() => proxyToBackend(req, "/api/v1/experiments", { method: "POST" }));
}
export async function GET(req: NextRequest) {
  return withErrors(() => proxyToBackend(req, "/api/v1/experiments"));
}
