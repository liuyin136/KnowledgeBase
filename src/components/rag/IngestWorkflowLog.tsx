import type { IngestPhase, IngestPhaseName } from "@/lib/api/ingest";

const PHASE_ORDER: IngestPhaseName[] = [
  "front_matter",
  "family_split",
  "parent_split",
  "child_split",
  "grandchild_split",
  "embed_family",
  "embed_parent",
  "embed_child",
  "embed_grandchild",
  "neo4j_upsert",
];

const PHASE_LABELS: Record<IngestPhaseName, string> = {
  front_matter: "Front-matter",
  family_split: "Family split",
  parent_split: "Parent AST split",
  child_split: "Child blocks",
  grandchild_split: "Grandchild sentences",
  embed_family: "Embed family",
  embed_parent: "Embed parents",
  embed_child: "Embed children",
  embed_grandchild: "Embed grandchildren",
  neo4j_upsert: "Neo4j upsert",
};

type StepStatus = "done" | "running" | "pending";

function phaseMetrics(phase: IngestPhase): string {
  const parts: string[] = [];
  if (phase.family_count != null) parts.push(`${phase.family_count} families`);
  if (phase.parent_count != null) parts.push(`${phase.parent_count} parents`);
  if (phase.child_count != null) parts.push(`${phase.child_count} children`);
  if (phase.grandchild_count != null) parts.push(`${phase.grandchild_count} grandchildren`);
  if (phase.embedded_count != null) parts.push(`${phase.embedded_count} embedded`);
  parts.push(`${phase.latency_ms} ms`);
  return parts.join(" · ");
}

function deriveStatus(
  phaseName: IngestPhaseName,
  phase: IngestPhase | undefined,
  activePhase: IngestPhaseName | null | undefined,
  loading: boolean
): StepStatus {
  if (phase) return "done";
  if (activePhase === phaseName) return "running";
  if (loading && !activePhase) return "running";
  return "pending";
}

export function IngestWorkflowLog({
  workflowLog,
  activePhase = null,
  loading = false,
  relativePath = null,
}: {
  workflowLog: IngestPhase[] | null;
  activePhase?: IngestPhaseName | null;
  loading?: boolean;
  relativePath?: string | null;
}) {
  if (!loading && (!workflowLog || workflowLog.length === 0) && !activePhase) {
    return null;
  }

  const byPhase = new Map(workflowLog?.map((p) => [p.phase, p]) ?? []);

  return (
    <section className="rag-panel rag-workflow" aria-live="polite" aria-label="Ingest workflow">
      <h2 className="rag-workflow-title">Ingest workflow</h2>
      {relativePath && <p className="rag-workflow-step-meta">File: {relativePath}</p>}
      <ol className="rag-workflow-list">
        {PHASE_ORDER.map((phaseName, i) => {
          const phase = byPhase.get(phaseName);
          const status = deriveStatus(phaseName, phase, activePhase, loading);
          const statusLabel =
            status === "running" ? "RUNNING" : status === "pending" ? "PENDING" : "DONE";
          return (
            <li key={phaseName} className={`rag-workflow-step rag-workflow-step--${status}`}>
              <div className="rag-workflow-step-header">
                <span className="rag-workflow-step-name">{PHASE_LABELS[phaseName]}</span>
                <span className={`rag-workflow-badge rag-workflow-badge--${status}`}>
                  {statusLabel}
                </span>
              </div>
              {phase && status === "done" && (
                <p className="rag-workflow-step-meta">{phaseMetrics(phase)}</p>
              )}
              {status === "running" && <p className="rag-workflow-step-meta">Processing…</p>}
              {i < PHASE_ORDER.length - 1 && (
                <span className="rag-workflow-connector" aria-hidden="true" />
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
