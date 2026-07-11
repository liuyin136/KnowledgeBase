export interface SearchRequest {
  query: string;
  w1?: number;
  w2?: number;
  recall_k?: number;
  rerank_k?: number;
  coarse_dim?: 256 | 512;
  use_minmax_fallback?: boolean;
  folder_ids?: string[] | null;
  created_after?: string | null;
  created_before?: string | null;
  indexed_only?: boolean;
}

export interface SearchHit {
  chunk_id: string;
  parent_path: string;
  chunk_index: number;
  content_preview: string;
  final_score: number;
  display_score: number;
  rerank_score?: number | null;
  file_id?: string | null;
  index_status?: string | null;
  relative_path?: string | null;
  parent_id?: string | null;
  child_id?: string | null;
  parent_content?: string | null;
  header_path?: string | null;
}

export type SearchJobStatus =
  | "awaiting_rerank"
  | "finished"
  | "skipped_rerank"
  | "rerank_started";

export interface RerankPreviewMeta {
  rerank_token_count: number;
  rerank_ctx_limit: number;
  rerank_doc_count: number;
  rerank_k: number;
}

export interface FusionMeta {
  pool_size: number;
  w1: number;
  w2: number;
  recall_k: number;
  rerank_k: number;
  coarse_dim: number;
  rescore_dim: number;
  latency_ms: number;
  vector_hit_count?: number;
  bm25_hit_count?: number;
  vram_peak_mb?: number;
  folder_ids?: string[] | null;
  created_after?: string | null;
  created_before?: string | null;
  indexed_only?: boolean | null;
  allowlist_size?: number | null;
}

export type WorkflowPhaseName =
  | "vault_scope"
  | "query_embed"
  | "coarse_ann"
  | "bm25_recall"
  | "rescore_1024"
  | "hybrid_fusion"
  | "rerank";

export interface WorkflowPhase {
  phase: WorkflowPhaseName;
  status: "done" | "skipped";
  latency_ms: number;
  model?: string | null;
  vram_peak_mb?: number | null;
  hit_count?: number | null;
  pool_size?: number | null;
  coarse_dim?: number | null;
  rescore_dim?: number | null;
  w1?: number | null;
  w2?: number | null;
  rerank_k?: number | null;
}

export interface SearchResponse {
  job_id?: string | null;
  span_id: string;
  cached: boolean;
  status?: SearchJobStatus | null;
  hits?: SearchHit[];
  fusion_meta?: FusionMeta;
  workflow_log?: WorkflowPhase[];
  rerank_preview?: RerankPreviewMeta | null;
  rerank_job_id?: string | null;
}

export interface RerankConfirmResponse {
  status: SearchJobStatus;
  rerank_job_id?: string | null;
  hits?: SearchHit[];
  fusion_meta?: FusionMeta;
  workflow_log?: WorkflowPhase[];
  span_id?: string | null;
  rerank_preview?: RerankPreviewMeta | null;
}

const API_BASE = "/api/v1/search";
const JOBS_BASE = "/api/v1/jobs";

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.text();
    let message = body || res.statusText;
    try {
      const parsed = JSON.parse(body) as { detail?: string };
      if (typeof parsed.detail === "string") message = parsed.detail;
    } catch {
      /* use raw body */
    }
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

export async function searchDocuments(body: SearchRequest): Promise<SearchResponse> {
  const res = await fetch(API_BASE, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handleResponse<SearchResponse>(res);
}

export async function confirmRerank(
  jobId: string,
  confirm: boolean
): Promise<RerankConfirmResponse> {
  const res = await fetch(`${JOBS_BASE}/${encodeURIComponent(jobId)}/rerank`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirm }),
  });
  return handleResponse<RerankConfirmResponse>(res);
}
