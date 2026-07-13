/** Graph search API — POST /api/v1/graph/search */

export interface GraphSearchRequest {
  mode: "local" | "global";
  seed_entity_id?: string;
  hops?: number;
  query?: string;
  top_communities?: number;
  memory_key?: string;
}

export interface GraphPath {
  entities: Record<string, unknown>[];
  relations: Record<string, unknown>[];
  claims: Record<string, unknown>[];
  community_id?: string;
}

export interface GraphSource {
  grandchild_id?: string;
  source_file?: string;
  fusion_score?: number;
}

export interface CommunitySummaryHit {
  community_id: string;
  level: number;
  text: string;
}

export interface GraphSearchResponse {
  paths: GraphPath[];
  community_summaries: CommunitySummaryHit[];
  sources: GraphSource[];
}

const API_BASE = "/api/v1/graph";

export async function graphSearch(body: GraphSearchRequest): Promise<GraphSearchResponse> {
  const res = await fetch(`${API_BASE}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `Graph search failed (${res.status})`);
  }
  return res.json() as Promise<GraphSearchResponse>;
}
