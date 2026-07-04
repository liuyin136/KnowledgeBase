/**
 * POST /api/v1/ingest — unified ingest. Returns 202 { jobId, experimentId, status }.
 * Body: { documentId, config: IngestConfig, experimentDescription? }
 *
 * Long-running: progress via GET /api/v1/ingest/[jobId]/status
 */
import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { IngestConfigSchema } from "@/lib/rag/types";
import { withErrors, parseBody, notFound } from "@/lib/rag/api-helpers";
import { ValidationError, NotFoundError } from "@/lib/rag/errors";
import * as store from "@/lib/rag/store";
import { createJob, dispatch } from "@/lib/rag/jobs";
import { ingestLongText, ingestChildChunk } from "@/lib/rag/orchestrator";

export async function POST(req: NextRequest) {
  return withErrors(async () => {
    const body = await parseBody<{
      documentId: string;
      config: { embeddingApproach: string; chunkMethod: string; advOption?: string };
      experimentDescription?: string;
    }>(req);
    if (!body.documentId) throw new ValidationError("documentId is required");

    const parsed = IngestConfigSchema.safeParse(body.config);
    if (!parsed.success) {
      throw new ValidationError("Invalid ingest config", { issues: parsed.error.issues });
    }
    const config = parsed.data;

    const doc = await store.getDocument(body.documentId);
    if (!doc) throw new NotFoundError(`Document ${body.documentId} not found`);

    const experimentId = await store.createExperiment({
      description: body.experimentDescription || `Ingest ${doc.filename}`,
      embeddingApproach: config.embeddingApproach,
      chunkMethod: config.embeddingApproach === "LongText" ? "LongText" : config.chunkMethod,
      sourceFile: doc.filename,
    });

    const jobId = await createJob({ type: "ingest", experimentId });

    // Dispatch background ingest.
    dispatch(async () => {
      if (config.embeddingApproach === "LongText") {
        await ingestLongText({ jobId, experimentId, documentId: doc.id, filename: doc.filename, text: doc.text, config });
      } else {
        await ingestChildChunk({ jobId, experimentId, documentId: doc.id, filename: doc.filename, text: doc.text, config });
      }
    });

    return NextResponse.json({ jobId, experimentId, status: "queued" }, { status: 202 });
  });
}
