/**
 * GET /api/v1/dashboard — system health + quick stats (Dashboard workflow).
 *   { experiments: {total, completed, failed}, documents, chunks, searches,
 *     memories, carts, recentExperiments, recentSearches, system: {...} }
 */
import { NextResponse } from "next/server";
import { withErrors } from "@/lib/rag/api-helpers";
import { db } from "@/lib/db";

export async function GET() {
  return withErrors(async () => {
    const [
      experimentCount,
      completedExperiments,
      failedExperiments,
      documents,
      chunks,
      searches,
      memories,
      carts,
      recentExperiments,
      recentSearches,
    ] = await Promise.all([
      db.experiment.count(),
      db.experiment.count({ where: { status: "completed" } }),
      db.experiment.count({ where: { status: "failed" } }),
      db.document.count(),
      db.knowledgeChunk.count(),
      db.searchRun.count(),
      db.memory.count(),
      db.memoryCart.count(),
      db.experiment.findMany({ orderBy: { createdAt: "desc" }, take: 5 }),
      db.searchRun.findMany({ orderBy: { createdAt: "desc" }, take: 5 }),
    ]);

    return NextResponse.json({
      stats: {
        experiments: { total: experimentCount, completed: completedExperiments, failed: failedExperiments },
        documents,
        chunks,
        searches,
        memories,
        carts,
      },
      recentExperiments,
      recentSearches,
      system: {
        embeddingModel: "LocalHash-1024 (v1 local-first; BGE-M3 drop-in target)",
        embeddingDim: 1024,
        stack: "Next.js 16 + Prisma/SQLite (adapted from FastAPI/Neo4j/Redis spec)",
        v1Scope: "Standard paths only — no Late/Agentic Chunking, no Structured Chat, no GraphRAG, no multi-user",
      },
    });
  });
}
