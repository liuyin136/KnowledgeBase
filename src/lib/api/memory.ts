/** Memory extract API — POST /api/v1/memory/extract */

import { pollJobUntilDone } from "./jobs";

export interface MemoryExtractRequest {
  query_text: string;
  grandchild_ids: string[];
  user_query_id?: string | null;
  session_id?: string | null;
}

export interface MemoryExtractResponse {
  job_id: string;
  trace_id: string;
}

export interface MemoryGraphJobResult {
  memory_id?: string;
  memory_key?: string;
  version?: number;
  entities_created?: number;
  relations_created?: number;
  claims_created?: number;
  communities_created?: number;
  summaries_created?: number;
}

export interface MemoryBundle {
  memory_key: string;
  memory_id?: string | null;
  content?: string | null;
  version: number;
  entity_count: number;
  claim_count: number;
  community_count: number;
  grandchild_count: number;
}

const API_BASE = "/api/v1/memory";

export async function extractMemory(
  body: MemoryExtractRequest
): Promise<MemoryExtractResponse> {
  const res = await fetch(`${API_BASE}/extract`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `Memory extract failed (${res.status})`);
  }
  return res.json() as Promise<MemoryExtractResponse>;
}

export async function getMemoryBundle(memoryKey: string): Promise<MemoryBundle> {
  const res = await fetch(`${API_BASE}/${encodeURIComponent(memoryKey)}`);
  if (!res.ok) {
    throw new Error(`Memory not found (${res.status})`);
  }
  return res.json() as Promise<MemoryBundle>;
}

export async function extractMemoryAndWait(
  body: MemoryExtractRequest,
  options?: { timeoutMs?: number }
): Promise<MemoryGraphJobResult> {
  const { job_id } = await extractMemory(body);
  const job = await pollJobUntilDone(job_id, {
    timeoutMs: options?.timeoutMs ?? 600_000,
  });
  if (job.status === "failed") {
    throw new Error(job.error || "Memory extract job failed");
  }
  return (job.result || {}) as MemoryGraphJobResult;
}
