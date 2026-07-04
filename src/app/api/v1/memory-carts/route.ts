/** POST /api/v1/memory-carts → proxy. GET → proxy. */
import { NextRequest } from "next/server";
import { proxyToBackend } from "@/lib/rag/backend-client";
import { withErrors } from "@/lib/rag/api-helpers";

export async function POST(req: NextRequest) {
  return withErrors(() => proxyToBackend(req, "/api/v1/memory-carts", { method: "POST" }));
}
export async function GET(req: NextRequest) {
  return withErrors(() => proxyToBackend(req, "/api/v1/memory-carts"));
}
