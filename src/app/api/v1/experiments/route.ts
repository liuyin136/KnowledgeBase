/**
 * POST /api/v1/experiments — create an experiment (ingest or search placeholder).
 * GET  /api/v1/experiments — paginated list (filter: ?kind=ingest|search).
 */
import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { IngestConfigSchema } from "@/lib/rag/types";
import { withErrors, parsePagination, parseBody } from "@/lib/rag/api-helpers";
import { ValidationError } from "@/lib/rag/errors";
import * as store from "@/lib/rag/store";

export async function POST(req: NextRequest) {
  return withErrors(async () => {
    const body = await parseBody<{
      description: string;
      config?: { embeddingApproach: string; chunkMethod: string };
      sourceFile?: string;
    }>(req);
    if (!body.description?.trim()) {
      throw new ValidationError("description is required");
    }
    let embeddingApproach = "LongText";
    let chunkMethod = "LongText";
    if (body.config) {
      const parsed = IngestConfigSchema.safeParse(body.config);
      if (!parsed.success) {
        throw new ValidationError("Invalid ingest config", { issues: parsed.error.issues });
      }
      embeddingApproach = parsed.data.embeddingApproach;
      chunkMethod = parsed.data.chunkMethod;
    }
    const id = await store.createExperiment({
      description: body.description,
      embeddingApproach,
      chunkMethod,
      sourceFile: body.sourceFile,
    });
    const exp = await db.experiment.findUnique({ where: { id } });
    return NextResponse.json(exp, { status: 201 });
  });
}

export async function GET(req: NextRequest) {
  return withErrors(async () => {
    const { page, pageSize } = parsePagination(req);
    const url = new URL(req.url);
    const rawKind = url.searchParams.get("kind");
    // Treat "all", "undefined", "" as no filter (defense against bad serialization).
    const kind = rawKind && rawKind !== "all" && rawKind !== "undefined"
      ? (rawKind as "ingest" | "search")
      : null;
    const { items, total } = await store.listExperiments({ page, pageSize, kind: kind ?? undefined });
    return NextResponse.json({
      items,
      total,
      page,
      pageSize,
      hasMore: page * pageSize < total,
    });
  });
}
