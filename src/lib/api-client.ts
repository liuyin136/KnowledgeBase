/**
 * Typed API client for the v1 REST contract.
 * Supports JSON + FormData (for multi-.md uploads).
 * Centralizes fetch + standardized error handling.
 */

import type {
  Paginated,
  ErrorBody,
  IngestConfig,
  SearchConfig,
  SearchResponse,
  ChunkMetadata,
  JobStatusResponse,
} from "@/lib/rag/types";

export class APIError extends Error {
  code: string;
  details?: Record<string, unknown>;
  status: number;
  constructor(body: ErrorBody, status: number) {
    super(body.error.message);
    this.code = body.error.code;
    this.details = body.error.details;
    this.status = status;
    this.name = "APIError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const bodyIsForm = init?.body instanceof FormData;
  const headers = bodyIsForm
    ? { ...(init?.headers || {}) }
    : { "Content-Type": "application/json", ...(init?.headers || {}) };
  const res = await fetch(path, {
    ...init,
    headers,
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    throw new APIError(data as ErrorBody, res.status);
  }
  return data as T;
}

/** Build a query string, dropping undefined/null/empty values (avoids "?kind=undefined"). */
function qs(params: Record<string, unknown> | undefined): string {
  if (!params) return "";
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export const api = {
  documents: {
    list: (params?: { page?: number; pageSize?: number }) =>
      request<Paginated<any>>(`/api/v1/documents${qs(params as Record<string, unknown> | undefined)}`),
    create: (body: { filename: string; text: string; contentType?: string }) =>
      request<{ ids: string[] }>(`/api/v1/documents`, { method: "POST", body: JSON.stringify(body) }),
    // New: multi-file .md upload (and single). Sends FormData with repeated 'file' entries.
    // Backend returns { ids: string[] }.
    upload: (formData: FormData) =>
      request<{ ids: string[] }>(`/api/v1/documents`, { method: "POST", body: formData }),
    delete: (id: string) => request<{ deleted: boolean }>(`/api/v1/documents/${id}`, { method: "DELETE" }),
    // Fetch full text for a document (raw Upload :Knowledge or ingested parent)
    getText: (id: string, kind: "upload" | "any" = "upload") =>
      request<any>(`/api/v1/documents/${id}/text${kind ? `?kind=${kind}` : ""}`),
    // For Documents page: chunks by source_file (using :Knowledge)
    chunks: (id: string) => request<{ items: ChunkMetadata[]; total: number }>(`/api/v1/documents/${id}/chunks`),
  },
  ingest: {
    start: (body: { documentId: string; config: IngestConfig; experimentDescription?: string }) =>
      request<{ jobId: string; experimentId: string; status: string }>(`/api/v1/ingest`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    status: (jobId: string) => request<JobStatusResponse>(`/api/v1/ingest/${jobId}/status`),
  },
  search: {
    start: (body: { rawQuery: string; config: SearchConfig }) =>
      request<{ jobId: string; searchId: string; status: string }>(`/api/v1/search`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    history: (params?: { page?: number; pageSize?: number }) =>
      request<Paginated<any>>(`/api/v1/searches/history${qs(params as Record<string, unknown> | undefined)}`),
  },
  jobs: {
    get: (jobId: string) => request<JobStatusResponse>(`/api/v1/jobs/${jobId}`),
  },
  memories: {
    list: (params?: { page?: number; pageSize?: number }) =>
      request<Paginated<any>>(`/api/v1/memories${qs(params as Record<string, unknown> | undefined)}`),
    create: (body: { userQueryId: string; queryText: string; chunkId?: string; chunkText?: string; notes?: string }) =>
      request<{ id: string }>(`/api/v1/memories`, { method: "POST", body: JSON.stringify(body) }),
  },
  memoryCarts: {
    list: () => request<{ items: any[]; total: number }>(`/api/v1/memory-carts`),
    create: (body: { name: string; description?: string }) =>
      request<{ id: string }>(`/api/v1/memory-carts`, { method: "POST", body: JSON.stringify(body) }),
    get: (id: string) => request<any>(`/api/v1/memory-carts/${id}`),
    patch: (id: string, body: { name?: string; description?: string; memoryIds?: string[]; addMemoryIds?: string[] }) =>
      request<any>(`/api/v1/memory-carts/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  },
  dashboard: () => request<any>(`/api/v1/dashboard`),
};

export type { SearchResponse };

/**
 * Detect a v1.2 backend-offline error (FastAPI unreachable).
 * Returns true when the API route proxied to the FastAPI backend and the backend
 * was unavailable/unreachable (HTTP 503 with BACKEND_UNAVAILABLE or
 * BACKEND_UNREACHABLE). Use this to show the shared <BackendOffline/> component
 * instead of a generic error state.
 */
export function isBackendOffline(err: unknown): boolean {
  return (
    err instanceof APIError &&
    (err.code === "BACKEND_UNAVAILABLE" || err.code === "BACKEND_UNREACHABLE")
  );
}
