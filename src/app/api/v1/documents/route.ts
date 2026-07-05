/** POST /api/v1/documents (JSON or multipart multi-file .md) → proxy (see backend-client.ts for multipart body forwarding rules). GET → proxy (paginated). */
import { NextRequest } from "next/server";
import { proxyToBackend } from "@/lib/rag/backend-client";
import { withErrors } from "@/lib/rag/api-helpers";

export async function POST(req: NextRequest) {
  return withErrors(() => proxyToBackend(req, "/api/v1/documents", { method: "POST" }));
}
export async function GET(req: NextRequest) {
  return withErrors(() => proxyToBackend(req, "/api/v1/documents"));
}
