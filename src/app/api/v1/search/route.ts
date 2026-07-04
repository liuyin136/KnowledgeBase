/** POST /api/v1/search → proxy (returns 202 + jobId + searchId). */
import { NextRequest } from "next/server";
import { proxyToBackend } from "@/lib/rag/backend-client";
import { withErrors } from "@/lib/rag/api-helpers";

export async function POST(req: NextRequest) {
  return withErrors(() => proxyToBackend(req, "/api/v1/search", { method: "POST" }));
}
