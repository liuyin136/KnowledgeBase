/** DELETE /api/v1/documents/[id] → proxy. */
import { NextRequest } from "next/server";
import { proxyToBackend } from "@/lib/rag/backend-client";
import { withErrors } from "@/lib/rag/api-helpers";

export async function DELETE(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  return withErrors(async () => {
    const { id } = await ctx.params;
    return proxyToBackend(req, `/api/v1/documents/${id}`, { method: "DELETE" });
  });
}
