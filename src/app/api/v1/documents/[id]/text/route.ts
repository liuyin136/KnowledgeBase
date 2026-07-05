/** GET /api/v1/documents/[id]/text → proxy to backend (supports ?kind=upload|any). */
import { NextRequest } from "next/server";
import { proxyToBackend } from "@/lib/rag/backend-client";
import { withErrors } from "@/lib/rag/api-helpers";

export async function GET(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  return withErrors(async () => {
    const { id } = await ctx.params;
    // Forward query (kind=...) automatically via proxy
    return proxyToBackend(req, `/api/v1/documents/${id}/text`, { forwardQuery: true });
  });
}
