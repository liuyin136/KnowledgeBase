/**
 * GET /api/v1/searches/history — paginated past searches.
 */
import { NextRequest, NextResponse } from "next/server";
import { withErrors, parsePagination } from "@/lib/rag/api-helpers";
import * as store from "@/lib/rag/store";

export async function GET(req: NextRequest) {
  return withErrors(async () => {
    const { page, pageSize } = parsePagination(req);
    const url = new URL(req.url);
    const experimentId = url.searchParams.get("experimentId") || undefined;
    const { items, total } = await store.listSearchRuns({ page, pageSize, experimentId });
    return NextResponse.json({ items, total, page, pageSize, hasMore: page * pageSize < total });
  });
}
