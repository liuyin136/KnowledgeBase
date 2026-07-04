/**
 * GET /api/v1/dashboard — system health + quick stats.
 * Proxies to the FastAPI backend for stats; adds Neo4j + backend health checks
 * so the Dashboard shows connection status (critical for the v1.2 Neo4j pivot).
 */
import { NextResponse, NextRequest } from "next/server";
import { proxyToBackend, isBackendConfigured, backendHealth } from "@/lib/rag/backend-client";
import { verifyNeo4jConnectivity, getNeo4jConfig } from "@/lib/rag/neo4j";
import { withErrors } from "@/lib/rag/api-helpers";
import { EMBEDDING_DIM } from "@/lib/rag/constants";

export async function GET() {
  return withErrors(async () => {
    const [backend, neo4jConn] = await Promise.all([backendHealth(), verifyNeo4jConnectivity()]);
    const cfg = getNeo4jConfig();

    // If backend is online, proxy the stats; otherwise return health-only payload.
    let stats: Record<string, unknown> | null = null;
    let recentExperiments: unknown[] = [];
    let recentSearches: unknown[] = [];
    if (backend.status === "online") {
      try {
        const req = new Request("http://internal/api/v1/dashboard");
        const resp = await proxyToBackend(new NextRequest(req), "/api/v1/dashboard");
        if (resp.status === 200) {
          const data = await resp.json();
          stats = data.stats ?? null;
          recentExperiments = data.recentExperiments ?? [];
          recentSearches = data.recentSearches ?? [];
        }
      } catch {
        /* fall through with null stats */
      }
    }

    return NextResponse.json({
      stats: stats ?? {
        experiments: { total: 0, completed: 0, failed: 0 },
        documents: 0,
        chunks: 0,
        searches: 0,
        memories: 0,
        carts: 0,
      },
      recentExperiments,
      recentSearches,
      system: {
        embeddingModel: "BAAI/bge-m3 (FastAPI backend, GPU)",
        embeddingDim: EMBEDDING_DIM,
        stack: "FastAPI + Neo4j 5.x + Redis + Next.js 16 (v1.2 — real directive stack)",
        v1Scope: "Standard paths only — no Late/Agentic Chunking, no Structured Chat, no GraphRAG, no multi-user",
      },
      health: {
        backend: { status: backend.status, configured: isBackendConfigured(), detail: backend.detail ?? null },
        neo4j: {
          status: neo4jConn.ok ? "online" : "offline",
          uri: cfg.uri,
          user: cfg.user,
          ...(neo4jConn.error ? { error: neo4jConn.error } : {}),
        },
      },
    });
  });
}
