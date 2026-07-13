export type IngestPhaseName =
  | "front_matter"
  | "family_split"
  | "parent_split"
  | "child_split"
  | "grandchild_split"
  | "embed_family"
  | "embed_parent"
  | "embed_child"
  | "embed_grandchild"
  | "neo4j_upsert";

export interface IngestPhase {
  phase: IngestPhaseName;
  status: "done" | "skipped";
  latency_ms: number;
  parent_count?: number | null;
  child_count?: number | null;
  grandchild_count?: number | null;
  family_count?: number | null;
  embedded_count?: number | null;
}

export interface IngestProgress {
  workflow_log: IngestPhase[];
  active_phase: IngestPhaseName | null;
  relative_path?: string | null;
}
