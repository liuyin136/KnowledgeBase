/** GET /api/v1/documents/[id]/chunks → proxy to FastAPI for :Knowledge + :KnowledgeChunk by source_file. */
import { NextRequest } from "next/server";
import { proxyToBackend } from "@/lib/rag/backend-client";
import { withErrors } from "@/lib/rag/api-helpers";

export async function GET(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  return withErrors(async () => {
    const { id } = await ctx.params;
    return proxyToBackend(req, `/api/v1/documents/${id}/chunks`);
  });
}
