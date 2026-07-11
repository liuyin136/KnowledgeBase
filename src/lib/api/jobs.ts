import type { IngestProgress } from "./ingest";
import type { FusionMeta, RerankPreviewMeta, SearchHit, WorkflowPhase, WorkflowPhaseName } from "./search";

export type JobPollStatus =
  | "queued"
  | "started"
  | "finished"
  | "failed"
  | "awaiting_rerank";

export interface SearchProgress {
  workflow_log: WorkflowPhase[];
  active_phase: WorkflowPhaseName | null;
  span_id?: string | null;
}

export interface JobStatusResponse {
  job_id: string;
  status: JobPollStatus;
  result?: {
    status?: string;
    hits?: SearchHit[];
    fusion_meta?: FusionMeta;
    workflow_log?: WorkflowPhase[];
    span_id?: string;
    rerank_token_count?: number;
    rerank_ctx_limit?: number;
    rerank_doc_count?: number;
  } | null;
  error?: string | null;
  rerank_preview?: RerankPreviewMeta | null;
  progress?: SearchProgress | null;
  ingest_progress?: IngestProgress | null;
}

const API_BASE = "/api/v1/jobs";

export async function getJobStatus(jobId: string): Promise<JobStatusResponse> {
  const res = await fetch(`${API_BASE}/${encodeURIComponent(jobId)}`);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || res.statusText);
  }
  return res.json() as Promise<JobStatusResponse>;
}

export interface PollJobOptions {
  intervalMs?: number;
  timeoutMs?: number;
  onProgress?: (status: JobStatusResponse) => void;
  untilStatuses?: JobPollStatus[];
}

export async function pollJobWithProgress(
  jobId: string,
  opts: PollJobOptions = {}
): Promise<JobStatusResponse> {
  const intervalMs = opts.intervalMs ?? 500;
  const timeoutMs = opts.timeoutMs ?? 120_000;
  const untilStatuses = opts.untilStatuses ?? ["finished", "failed"];
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const status = await getJobStatus(jobId);
    opts.onProgress?.(status);
    if (untilStatuses.includes(status.status)) {
      return status;
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error("Job polling timed out");
}

export async function pollJobUntilDone(
  jobId: string,
  opts: { intervalMs?: number; timeoutMs?: number; onProgress?: (status: JobStatusResponse) => void } = {}
): Promise<JobStatusResponse> {
  return pollJobWithProgress(jobId, {
    ...opts,
    untilStatuses: ["finished", "failed"],
  });
}

export async function pollJobUntilAwaitingOrDone(
  jobId: string,
  opts: { intervalMs?: number; timeoutMs?: number; onProgress?: (status: JobStatusResponse) => void } = {}
): Promise<JobStatusResponse> {
  return pollJobWithProgress(jobId, {
    ...opts,
    untilStatuses: ["awaiting_rerank", "finished", "failed"],
  });
}
