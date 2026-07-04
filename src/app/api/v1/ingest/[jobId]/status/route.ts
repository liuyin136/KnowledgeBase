/**
 * GET /api/v1/ingest/[jobId]/status — poll ingest job progress.
 */
import { NextRequest, NextResponse } from "next/server";
import { withErrors, notFound } from "@/lib/rag/api-helpers";
import { getJobStatus } from "@/lib/rag/jobs";

export async function GET(_req: NextRequest, ctx: { params: Promise<{ jobId: string }> }) {
  return withErrors(async () => {
    const { jobId } = await ctx.params;
    const status = await getJobStatus(jobId);
    if (!status) return notFound(`Job ${jobId} not found`);
    return NextResponse.json(status);
  });
}
