/** GET /api/v1/ingest/[jobId]/status → proxy. */
import { NextRequest } from "next/server";
import { proxyToBackend } from "@/lib/rag/backend-client";
import { withErrors } from "@/lib/rag/api-helpers";

export async function GET(req: NextRequest, ctx: { params: Promise<{ jobId: string }> }) {
  return withErrors(async () => {
    const { jobId } = await ctx.params;
    return proxyToBackend(req, `/api/v1/ingest/${jobId}/status`);
  });
}
