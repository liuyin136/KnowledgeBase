/**
 * JobRegistry — in-memory + SQLite-persisted job state for long-running ingest/search.
 * Replaces Redis + RQ worker from the infrastructure spec (this sandbox is single-process
 * Next.js; background "jobs" run via setImmediate micro-tasks with progress persisted to
 * the Job table for resilience across requests / polling).
 *
 * Mirrors workers/tasks.py + workers/progress.py from backend-directory-structure spec.
 */

import { db } from "@/lib/db";
import type { IngestProgressEvent, JobStatus, JobType, SearchResponse } from "./types";
import { logPipelineEvent } from "./errors";

interface RunningJob {
  jobId: string;
  abort?: AbortController;
}

const running = new Map<string, RunningJob>();

/** Create a job record (status=queued) and return its id. */
export async function createJob(opts: {
  type: JobType;
  experimentId?: string | null;
  total?: number;
}): Promise<string> {
  const job = await db.job.create({
    data: {
      type: opts.type,
      experimentId: opts.experimentId ?? null,
      status: "queued",
      total: opts.total ?? 0,
    },
  });
  logPipelineEvent({ event: "job.created", jobId: job.id, type: opts.type });
  return job.id;
}

/** Mark a job running. */
export async function markRunning(jobId: string, total?: number): Promise<void> {
  await db.job.update({
    where: { id: jobId },
    data: { status: "running", ...(total !== undefined ? { total } : {}) },
  });
  logPipelineEvent({ event: "job.running", jobId });
}

/** Append a progress event (per-chunk metadata) to the job. */
export async function appendEvent(
  jobId: string,
  event: IngestProgressEvent,
): Promise<void> {
  const job = await db.job.findUnique({ where: { id: jobId } });
  if (!job) return;
  const events = JSON.parse(job.events || "[]") as IngestProgressEvent[];
  events.push(event);
  await db.job.update({
    where: { id: jobId },
    data: {
      events: JSON.stringify(events),
      current: event.index,
      total: event.total,
      progress: event.progress,
    },
  });
}

/** Mark a job completed. */
export async function markCompleted(
  jobId: string,
  result?: SearchResponse,
): Promise<void> {
  await db.job.update({
    where: { id: jobId },
    data: {
      status: "completed",
      progress: 100,
      ...(result ? { result: JSON.stringify(result) } : {}),
    },
  });
  const r = running.get(jobId);
  if (r) running.delete(jobId);
  logPipelineEvent({ event: "job.completed", jobId });
}

/** Mark a job failed with error details. */
export async function markFailed(
  jobId: string,
  code: string,
  message: string,
): Promise<void> {
  await db.job.update({
    where: { id: jobId },
    data: { status: "failed", errorCode: code, errorMessage: message },
  });
  const r = running.get(jobId);
  if (r) running.delete(jobId);
  logPipelineEvent({ event: "job.failed", jobId, errorCode: code });
}

/** Register an in-memory abort controller for cancellation. */
export function registerAbort(jobId: string, controller: AbortController): void {
  running.set(jobId, { jobId, abort: controller });
}

/** Cancel a running job (best-effort). */
export async function cancelJob(jobId: string): Promise<boolean> {
  const r = running.get(jobId);
  if (r?.abort) {
    r.abort.abort();
    await markFailed(jobId, "CANCELLED", "Job cancelled by user");
    return true;
  }
  return false;
}

/** Read full job state for the status endpoint. */
export async function getJobStatus(jobId: string) {
  const job = await db.job.findUnique({ where: { id: jobId } });
  if (!job) return null;
  return {
    jobId: job.id,
    type: job.type as JobType,
    experimentId: job.experimentId,
    status: job.status as JobStatus,
    progress: job.progress,
    current: job.current,
    total: job.total,
    events: JSON.parse(job.events || "[]") as IngestProgressEvent[],
    errorCode: job.errorCode,
    errorMessage: job.errorMessage,
    result: job.result ? (JSON.parse(job.result) as SearchResponse) : null,
  };
}

/** Fire-and-forget a long task (simulates background worker dispatch). */
export function dispatch(task: () => Promise<void>): void {
  // Use setImmediate-like scheduling to return to the event loop quickly.
  Promise.resolve()
    .then(() => task())
    .catch((err) => {
      logPipelineEvent({
        event: "job.dispatch_error",
        error: err instanceof Error ? err.message : String(err),
      });
    });
}
