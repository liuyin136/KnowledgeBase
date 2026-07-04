/** GET /api/v1/searches/history → proxy. */
import { NextRequest } from "next/server";
import { proxyToBackend } from "@/lib/rag/backend-client";
import { withErrors } from "@/lib/rag/api-helpers";

export async function GET(req: NextRequest) {
  return withErrors(() => proxyToBackend(req, "/api/v1/searches/history"));
}
