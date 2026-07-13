"use client";

import type { IngestPhase, IngestPhaseName } from "@/lib/api/ingest";
import { IngestWorkflowLog } from "@/components/rag/IngestWorkflowLog";

export type MigrateFileStatus = "pending" | "running" | "done" | "failed";

export interface MigrateFileEntry {
  fileId: string;
  relativePath: string;
  jobId: string;
  status: MigrateFileStatus;
  error?: string | null;
}

export function VaultMigrateProgress({
  files,
  currentIndex,
  workflowLog,
  activePhase,
  relativePath,
}: {
  files: MigrateFileEntry[];
  currentIndex: number;
  workflowLog: IngestPhase[] | null;
  activePhase: IngestPhaseName | null;
  relativePath: string | null;
}) {
  const total = files.length;
  const doneCount = files.filter((f) => f.status === "done").length;
  const failedCount = files.filter((f) => f.status === "failed").length;

  return (
    <section className="rag-panel" aria-live="polite" aria-label="Vault migration progress">
      <h2 className="rag-workflow-title">Migrate &amp; Reindex All</h2>
      <p className="rag-workflow-step-meta">
        File {Math.min(currentIndex + 1, total)}/{total} · {doneCount} done
        {failedCount > 0 ? ` · ${failedCount} failed` : ""}
      </p>
      <IngestWorkflowLog
        workflowLog={workflowLog}
        activePhase={activePhase}
        loading={files.some((f) => f.status === "running")}
        relativePath={relativePath}
      />
      <ul className="rag-workflow-list" style={{ marginTop: "1rem" }}>
        {files.map((f) => (
          <li key={f.fileId} className={`rag-workflow-step rag-workflow-step--${f.status === "running" ? "running" : f.status === "done" ? "done" : f.status === "failed" ? "failed" : "pending"}`}>
            <code>{f.relativePath}</code>
            {" — "}
            {f.status === "done" && "DONE"}
            {f.status === "failed" && (f.error || "FAILED")}
            {f.status === "running" && "RUNNING"}
            {f.status === "pending" && "PENDING"}
          </li>
        ))}
      </ul>
    </section>
  );
}
