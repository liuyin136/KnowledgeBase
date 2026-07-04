/**
 * GET /api/v1/experiments/[id]/chunks — observability: all chunk metadata for an experiment.
 */
import { NextRequest, NextResponse } from "next/server";
import { withErrors, notFound } from "@/lib/rag/api-helpers";
import { db } from "@/lib/db";

export async function GET(_req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  return withErrors(async () => {
    const { id } = await ctx.params;
    const exp = await db.experiment.findUnique({ where: { id } });
    if (!exp) return notFound(`Experiment ${id} not found`);
    const chunks = await db.knowledgeChunk.findMany({
      where: { experimentId: id },
      orderBy: { chunkIndex: "asc" },
      include: { parent: { select: { sourceFile: true, text: true } } },
    });
    const items = chunks.map((c) => ({
      chunkId: c.id,
      parentDocId: c.parentId,
      experimentId: c.experimentId,
      chunkIndex: c.chunkIndex,
      chunkMethod: c.chunkMethod,
      embeddingMethod: c.embeddingMethod,
      tokenCount: c.tokenCount,
      chunkingTimeMs: c.chunkingTimeMs,
      embeddingTimeMs: c.embeddingTimeMs,
      charStart: c.charStart,
      charEnd: c.charEnd,
      section: c.section,
      text: c.text,
      textPreview: c.text.slice(0, 220) + (c.text.length > 220 ? "…" : ""),
      parentSourceFile: c.parent.sourceFile,
    }));
    return NextResponse.json({ items, total: items.length });
  });
}
