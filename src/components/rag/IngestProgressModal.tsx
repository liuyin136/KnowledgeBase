"use client";

import type { IngestPhase, IngestPhaseName } from "@/lib/api/ingest";
import { IngestWorkflowLog } from "@/components/rag/IngestWorkflowLog";

export function IngestProgressModal({
  open,
  title,
  relativePath,
  workflowLog,
  activePhase,
  loading,
  onClose,
}: {
  open: boolean;
  title: string;
  relativePath: string | null;
  workflowLog: IngestPhase[] | null;
  activePhase: IngestPhaseName | null;
  loading: boolean;
  onClose: () => void;
}) {
  if (!open) return null;

  return (
    <div
      className="rag-modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="ingest-progress-title"
      onClick={onClose}
    >
      <div className="rag-modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 640 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h3 id="ingest-progress-title" style={{ marginTop: 0 }}>
            {title}
          </h3>
          <button
            type="button"
            className="rag-button rag-button--ghost"
            disabled={loading}
            onClick={onClose}
          >
            {loading ? "Ingesting…" : "Close"}
          </button>
        </div>
        <IngestWorkflowLog
          workflowLog={workflowLog}
          activePhase={activePhase}
          loading={loading}
          relativePath={relativePath}
        />
      </div>
    </div>
  );
}
