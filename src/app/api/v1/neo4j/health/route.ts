/**
 * GET /api/v1/neo4j/health — Neo4j connectivity check (for Dashboard system card).
 */
import { NextResponse } from "next/server";
import { verifyNeo4jConnectivity, getNeo4jConfig } from "@/lib/rag/neo4j";
import { withErrors } from "@/lib/rag/api-helpers";

export async function GET() {
  return withErrors(async () => {
    const { ok, error } = await verifyNeo4jConnectivity();
    const cfg = getNeo4jConfig();
    return NextResponse.json({
      status: ok ? "online" : "offline",
      uri: cfg.uri,
      user: cfg.user,
      ...(error ? { error } : {}),
    });
  });
}
