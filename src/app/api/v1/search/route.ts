/**
 * POST /api/v1/search — hybrid search. Returns 202 { jobId, searchId } for long-running.
 * Body: { rawQuery, config: SearchConfig, experimentId? }
 *
 * The search itself runs quickly for v1-scale corpora, but we follow the contract
 * (202 + jobId) so the frontend can poll progress + the future Python stack can
 * run true long searches with the same client code.
 */
import { NextRequest, NextResponse } from "next/server";
import { randomUUID } from "crypto";
import { SearchConfigSchema } from "@/lib/rag/types";
import { withErrors, parseBody } from "@/lib/rag/api-helpers";
import { ValidationError } from "@/lib/rag/errors";
import { createJob, dispatch } from "@/lib/rag/jobs";
import { runSearch } from "@/lib/rag/orchestrator";

export async function POST(req: NextRequest) {
  return withErrors(async () => {
    const body = await parseBody<{
      rawQuery: string;
      config: Record<string, unknown>;
      experimentId?: string;
    }>(req);
    if (!body.rawQuery?.trim()) throw new ValidationError("rawQuery is required");

    const parsed = SearchConfigSchema.safeParse(body.config ?? {});
    if (!parsed.success) {
      throw new ValidationError("Invalid search config", { issues: parsed.error.issues });
    }
    const config = parsed.data;
    const searchId = randomUUID();
    const jobId = await createJob({ type: "search", experimentId: body.experimentId ?? null });

    // Dispatch background search.
    dispatch(async () => {
      await runSearch({
        jobId,
        searchId,
        rawQuery: body.rawQuery,
        config,
        experimentId: body.experimentId ?? null,
      });
    });

    return NextResponse.json({ jobId, searchId, status: "queued" }, { status: 202 });
  });
}
