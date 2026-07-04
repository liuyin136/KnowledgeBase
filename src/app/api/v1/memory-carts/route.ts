/**
 * POST /api/v1/memory-carts — create a cart.
 * GET  /api/v1/memory-carts — list carts.
 */
import { NextRequest, NextResponse } from "next/server";
import { withErrors, parseBody } from "@/lib/rag/api-helpers";
import { ValidationError } from "@/lib/rag/errors";
import * as store from "@/lib/rag/store";

export async function POST(req: NextRequest) {
  return withErrors(async () => {
    const body = await parseBody<{ name: string; description?: string }>(req);
    if (!body.name?.trim()) throw new ValidationError("name is required");
    const id = await store.createMemoryCart({ name: body.name, description: body.description });
    return NextResponse.json({ id }, { status: 201 });
  });
}

export async function GET() {
  return withErrors(async () => {
    const items = await store.listMemoryCarts();
    return NextResponse.json({ items, total: items.length });
  });
}
