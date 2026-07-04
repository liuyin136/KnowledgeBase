/**
 * DELETE /api/v1/documents/[id]
 */
import { NextRequest, NextResponse } from "next/server";
import { withErrors, notFound } from "@/lib/rag/api-helpers";
import * as store from "@/lib/rag/store";

export async function DELETE(_req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  return withErrors(async () => {
    const { id } = await ctx.params;
    const doc = await store.getDocument(id);
    if (!doc) return notFound(`Document ${id} not found`);
    await store.deleteDocument(id);
    return NextResponse.json({ deleted: true, id });
  });
}
