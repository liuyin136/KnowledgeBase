/** POST /api/v1/seed → proxy to FastAPI backend (seeds sample documents into Neo4j). */
import { NextRequest } from "next/server";
import { proxyToBackend } from "@/lib/rag/backend-client";
import { withErrors } from "@/lib/rag/api-helpers";

export async function POST(req: NextRequest) {
  return withErrors(() => proxyToBackend(req, "/api/v1/seed", { method: "POST" }));
}
