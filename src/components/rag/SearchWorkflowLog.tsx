import type { FusionMeta, WorkflowPhase, WorkflowPhaseName } from "@/lib/api/search";

const BASE_PHASE_ORDER: WorkflowPhaseName[] = [
  "query_embed",
  "family_recall",
  "parent_recall",
  "child_recall",
  "grandchild_recall",
  "hierarchical_fusion",
  "rerank",
];

const PHASE_LABELS: Record<WorkflowPhaseName, string> = {
  vault_scope: "Vault scope",
  query_embed: "Query embed",
  family_recall: "W1 Family recall",
  parent_recall: "W2 Parent recall",
  child_recall: "W3 Child recall",
  grandchild_recall: "W4 Grandchild recall",
  hierarchical_fusion: "Hierarchical fusion",
  rerank: "W5 Rerank",
  coarse_ann: "Coarse ANN recall",
  bm25_recall: "BM25 recall",
  rescore_1024: "1024d rescore",
  hybrid_fusion: "Hybrid fusion",
};

function phaseOrder(
  workflowLog: WorkflowPhase[] | null,
  activePhase: WorkflowPhaseName | null | undefined,
  showVaultScope: boolean
): WorkflowPhaseName[] {
  const hasVault =
    showVaultScope ||
    workflowLog?.some((p) => p.phase === "vault_scope") ||
    activePhase === "vault_scope";
  return hasVault ? ["vault_scope", ...BASE_PHASE_ORDER] : BASE_PHASE_ORDER;
}

function phaseMetrics(phase: WorkflowPhase): string {
  const parts: string[] = [];
  if (phase.model) parts.push(phase.model);
  if (phase.hit_count != null) parts.push(`hits ${phase.hit_count}`);
  if (phase.pool_size != null) parts.push(`pool ${phase.pool_size}`);
  if (phase.coarse_dim != null) parts.push(`${phase.coarse_dim}d`);
  if (phase.rescore_dim != null) parts.push(`${phase.rescore_dim}d`);
  if (phase.w1 != null && phase.w2 != null) parts.push(`w1=${phase.w1} w2=${phase.w2}`);
  if (phase.rerank_k != null && phase.phase !== "hierarchical_fusion") parts.push(`top ${phase.rerank_k}`);
  if (phase.vram_peak_mb != null) parts.push(`VRAM ${phase.vram_peak_mb} MB`);
  parts.push(`${phase.latency_ms} ms`);
  return parts.join(" · ");
}

type StepStatus = "done" | "running" | "cached" | "skipped" | "awaiting" | "pending";

function deriveStepStatus(
  phaseName: WorkflowPhaseName,
  phase: WorkflowPhase | undefined,
  activePhase: WorkflowPhaseName | null | undefined,
  awaitingRerank: boolean,
  cached: boolean,
  loading: boolean
): StepStatus {
  if (phase) {
    if (cached && phase.status === "skipped") return "skipped";
    if (cached) return "cached";
    return "done";
  }
  if (awaitingRerank && phaseName === "rerank") return "awaiting";
  if (activePhase === phaseName) return "running";
  if (loading && !activePhase) return "running";
  return "pending";
}

function WorkflowStep({
  phaseName,
  phase,
  status,
  isLast,
  rerankPreview,
}: {
  phaseName: WorkflowPhaseName;
  phase?: WorkflowPhase;
  status: StepStatus;
  isLast: boolean;
  rerankPreview?: { rerank_token_count: number; rerank_ctx_limit: number } | null;
}) {
  const label = PHASE_LABELS[phaseName];
  const statusLabel =
    status === "running"
      ? "RUNNING"
      : status === "cached"
        ? "CACHED"
        : status === "skipped"
          ? "SKIPPED"
          : status === "awaiting"
            ? "AWAITING"
            : status === "pending"
              ? "PENDING"
              : "DONE";

  return (
    <li className={`rag-workflow-step rag-workflow-step--${status}`}>
      <div className="rag-workflow-step-header">
        <span className="rag-workflow-step-name">{label}</span>
        <span className={`rag-workflow-badge rag-workflow-badge--${status}`}>{statusLabel}</span>
      </div>
      {phase && status !== "running" && status !== "awaiting" && status !== "pending" && (
        <p className="rag-workflow-step-meta">{phaseMetrics(phase)}</p>
      )}
      {status === "running" && <p className="rag-workflow-step-meta">Processing…</p>}
      {status === "awaiting" && rerankPreview && (
        <p className="rag-workflow-step-meta">
          {rerankPreview.rerank_token_count.toLocaleString()} tokens · limit{" "}
          {rerankPreview.rerank_ctx_limit.toLocaleString()} · awaiting confirmation
        </p>
      )}
      {!isLast && <span className="rag-workflow-connector" aria-hidden="true" />}
    </li>
  );
}

export function SearchWorkflowLog({
  workflowLog,
  fusionMeta,
  cached,
  loading,
  activePhase = null,
  showVaultScope = false,
  awaitingRerank = false,
  rerankPreview = null,
}: {
  workflowLog: WorkflowPhase[] | null;
  fusionMeta: FusionMeta | null;
  cached: boolean;
  loading: boolean;
  activePhase?: WorkflowPhaseName | null;
  showVaultScope?: boolean;
  awaitingRerank?: boolean;
  rerankPreview?: { rerank_token_count: number; rerank_ctx_limit: number } | null;
}) {
  const hasActivity = loading || (workflowLog && workflowLog.length > 0) || activePhase;
  if (!hasActivity) {
    return null;
  }

  const byPhase = new Map(workflowLog?.map((p) => [p.phase, p]) ?? []);
  const order = phaseOrder(workflowLog, activePhase, showVaultScope);

  return (
    <section className="rag-panel rag-workflow" aria-live="polite" aria-label="Search workflow">
      <h2 className="rag-workflow-title">Search workflow</h2>
      {cached && <p className="rag-cached">CACHED</p>}
      <ol className="rag-workflow-list">
        {order.map((phaseName, i) => {
          const phase = byPhase.get(phaseName);
          const status = deriveStepStatus(
            phaseName,
            phase,
            activePhase,
            awaitingRerank,
            cached,
            loading
          );
          return (
            <WorkflowStep
              key={phaseName}
              phaseName={phaseName}
              phase={phase}
              status={status}
              isLast={i === order.length - 1}
              rerankPreview={phaseName === "rerank" ? rerankPreview : null}
            />
          );
        })}
      </ol>
      {fusionMeta && !loading && (
        <footer className="rag-workflow-summary">
          Total {fusionMeta.latency_ms} ms
          {(fusionMeta.vram_peak_mb ?? 0) > 0 && <> · VRAM peak {fusionMeta.vram_peak_mb} MB</>}
          {fusionMeta.allowlist_size != null && (
            <> · Allowlist {fusionMeta.allowlist_size} paths</>
          )}
          {fusionMeta.rerank_over_limit && <> · Rerank over 8192-token gate</>}
        </footer>
      )}
    </section>
  );
}
