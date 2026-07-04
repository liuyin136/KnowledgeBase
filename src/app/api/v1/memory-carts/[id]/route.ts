/**
 * GET   /api/v1/memory-carts/[id] — cart detail with selected memories.
 * PATCH /api/v1/memory-carts/[id] — update cart (name/description/memoryIds selection).
 */
import { NextRequest, NextResponse } from "next/server";
import { withErrors, notFound, parseBody } from "@/lib/rag/api-helpers";
import { ValidationError } from "@/lib/rag/errors";
import * as store from "@/lib/rag/store";

export async function GET(_req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  return withErrors(async () => {
    const { id } = await ctx.params;
    const cart = await store.getMemoryCart(id);
    if (!cart) return notFound(`MemoryCart ${id} not found`);
    return NextResponse.json(cart);
  });
}

export async function PATCH(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  return withErrors(async () => {
    const { id } = await ctx.params;
    const body = await parseBody<{
      name?: string;
      description?: string;
      memoryIds?: string[]; // replace selection
      addMemoryIds?: string[]; // additive
    }>(req);
    const existing = await store.getMemoryCart(id);
    if (!existing) return notFound(`MemoryCart ${id} not found`);

    if (body.name !== undefined || body.description !== undefined) {
      const { db } = await import("@/lib/db");
      await db.memoryCart.update({
        where: { id },
        data: {
          ...(body.name !== undefined ? { name: body.name } : {}),
          ...(body.description !== undefined ? { description: body.description } : {}),
        },
      });
    }
    if (Array.isArray(body.memoryIds)) {
      await store.setCartMemorySelection(id, body.memoryIds);
    } else if (Array.isArray(body.addMemoryIds) && body.addMemoryIds.length > 0) {
      await store.addMemoriesToCart(id, body.addMemoryIds);
    } else {
      throw new ValidationError("Nothing to update; provide name, description, memoryIds, or addMemoryIds");
    }
    const updated = await store.getMemoryCart(id);
    return NextResponse.json(updated);
  });
}
