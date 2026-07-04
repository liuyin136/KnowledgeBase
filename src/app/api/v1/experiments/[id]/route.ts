/**
 * GET /api/v1/experiments/[id] — single experiment detail.
 */
import { NextRequest, NextResponse } from "next/server";
import { withErrors, notFound } from "@/lib/rag/api-helpers";
import * as store from "@/lib/rag/store";

export async function GET(_req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  return withErrors(async () => {
    const { id } = await ctx.params;
    const exp = await store.getExperiment(id);
    if (!exp) return notFound(`Experiment ${id} not found`);
    return NextResponse.json(exp);
  });
}
