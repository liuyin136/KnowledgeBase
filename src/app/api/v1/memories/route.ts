/**
 * GET  /api/v1/memories — paginated memories (filter: ?experimentId=).
 * POST /api/v1/memories — create a memory manually (usually created automatically by search).
 */
import { NextRequest, NextResponse } from "next/server";
import { withErrors, parsePagination, parseBody } from "@/lib/rag/api-helpers";
import { ValidationError } from "@/lib/rag/errors";
import * as store from "@/lib/rag/store";

export async function GET(req: NextRequest) {
  return withErrors(async () => {
    const { page, pageSize } = parsePagination(req);
    const url = new URL(req.url);
    const experimentId = url.searchParams.get("experimentId") || undefined;
    const { items, total } = await store.listMemories({ page, pageSize, experimentId });
    return NextResponse.json({ items, total, page, pageSize, hasMore: page * pageSize < total });
  });
}

export async function POST(req: NextRequest) {
  return withErrors(async () => {
    const body = await parseBody<{
      userQueryId: string;
      experimentId?: string;
      chunkId?: string;
      queryText: string;
      chunkText?: string;
      notes?: string;
    }>(req);
    if (!body.userQueryId) throw new ValidationError("userQueryId is required");
    if (!body.queryText) throw new ValidationError("queryText is required");
    const id = await store.createMemory({
      userQueryId: body.userQueryId,
      experimentId: body.experimentId ?? null,
      chunkId: body.chunkId ?? null,
      queryText: body.queryText,
      chunkText: body.chunkText ?? null,
      notes: body.notes ?? null,
    });
    return NextResponse.json({ id }, { status: 201 });
  });
}
