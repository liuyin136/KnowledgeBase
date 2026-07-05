/**
 * GET /api/v1/dashboard — system health + quick stats.
 * Proxies to the FastAPI backend for stats; adds Neo4j + backend health checks
 * so the Dashboard shows connection status (critical for the v1.2 Neo4j pivot).
 *
 * v1.3: when the backend is online, we forward its `system` block verbatim
 * (which now includes `embeddingModel`, `embeddingModelLogical`,
 * `embeddingNativeDim`, `rerankerModel`, `rerankerModelLogical`, and
 * `rerankerMaxLength`) so the Settings view can display the ACTIVE models.
 * When the backend is offline we fall back to a v1.3 default system block
 * (Jina v5 small + Jina Reranker v3) so the UI still renders.
 */
import { NextResponse, NextRequest } from "next/server";
import { proxyToBackend, isBackendConfigured, backendHealth } from "@/lib/rag/backend-client";
import { verifyNeo4jConnectivity, getNeo4jConfig } from "@/lib/rag/neo4j";
import { withErrors } from "@/lib/rag/api-helpers";
import { EMBEDDING_DIM, EMBEDDING_MODEL, RERANKER_MODEL } from "@/lib/rag/constants";

export async function GET() {
  return withErrors(async () => {
    const [backend, neo4jConn] = await Promise.all([backendHealth(), verifyNeo4jConnectivity()]);
    const cfg = getNeo4jConfig();

    // If backend is online, proxy the stats; otherwise return health-only payload.
    let stats: Record<string, unknown> | null = null;
    let recentExperiments: unknown[] = [];
    let recentSearches: unknown[] = [];
    let system: Record<string, unknown> | null = null;
    if (backend.status === "online") {
      try {
        const req = new Request("http://internal/api/v1/dashboard");
        const resp = await proxyToBackend(new NextRequest(req), "/api/v1/dashboard");
        if (resp.status === 200) {
          const data = await resp.json();
          stats = data.stats ?? null;
          recentExperiments = data.recentExperiments ?? [];
          recentSearches = data.recentSearches ?? [];
          // v1.3: forward the backend's system block verbatim — it now contains
          // the active model repo ids + logical ids + native dims + reranker
          // max length, which the Settings view depends on.
          if (data.system && typeof data.system === "object") {
            system = data.system;
          }
        }
      } catch {
        /* fall through with null stats + null system */
      }
    }

    // Fallback system block (v1.3 defaults) — used when backend is offline OR
    // the backend response didn't include a `system` field.
    if (!system) {
      system = {
        embeddingModel: EMBEDDING_MODEL,
        embeddingModelLogical: "jina-v5-small",
        embeddingDim: EMBEDDING_DIM,
        embeddingNativeDim: 1536,
        rerankerModel: RERANKER_MODEL,
        rerankerModelLogical: "jina-v3",
        rerankerMaxLength: 8192,
        stack: "FastAPI + Neo4j 5.x + Redis + Next.js 16 (v1.3 — Jina v5 default + BGE-M3 toggle)",
        v1Scope: "Standard paths only — no Late/Agentic Chunking, no Structured Chat, no GraphRAG, no multi-user",
      };
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
      system,
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
