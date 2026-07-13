"use client";

import type { IngestPreviewResponse } from "@/lib/api/vault";

export function IngestConfirmDialog({
  open,
  preview,
  confirming,
  onConfirm,
  onClose,
}: {
  open: boolean;
  preview: IngestPreviewResponse | null;
  confirming: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  if (!open || !preview) return null;

  const softGate = 50_000;
  const overSoftGate = preview.total_estimated_tokens > softGate;
  const ratio = Math.min(100, (preview.total_estimated_tokens / softGate) * 100);
  const blocked = preview.items.filter((i) => !i.ingestible);

  return (
    <div
      className="rag-modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="ingest-confirm-title"
      onClick={onClose}
    >
      <div className="rag-modal rag-rerank-confirm" onClick={(e) => e.stopPropagation()}>
        <h3 id="ingest-confirm-title" style={{ marginTop: 0 }}>
          Confirm ingest
        </h3>
        <p className="rag-rerank-confirm-lead">
          Ingestion builds the Neo4j search index (chunking + GPU embed). Files stay searchable
          only after ingest completes.
        </p>

        <dl className="rag-rerank-confirm-stats">
          <div>
            <dt>Files to ingest</dt>
            <dd>{preview.file_count}</dd>
          </div>
          <div>
            <dt>Estimated tokens</dt>
            <dd className="rag-rerank-confirm-tokens">
              {preview.total_estimated_tokens.toLocaleString()}
            </dd>
          </div>
          <div>
            <dt>Soft warning threshold</dt>
            <dd>{softGate.toLocaleString()}</dd>
          </div>
        </dl>

        <div className="rag-rerank-confirm-bar" aria-hidden="true">
          <div
            className={`rag-rerank-confirm-fill${overSoftGate ? " rag-rerank-confirm-fill--over" : ""}`}
            style={{ width: `${ratio}%` }}
          />
        </div>

        {overSoftGate && (
          <p className="rag-error rag-rerank-confirm-warn">
            Estimated token load exceeds {softGate.toLocaleString()}. Large batches may take a long
            time on GPU.
          </p>
        )}

        {blocked.length > 0 && (
          <p className="rag-error rag-rerank-confirm-warn">
            {blocked.length} file(s) cannot be ingested (locked or missing).
          </p>
        )}

        <div className="rag-rerank-confirm-actions">
          <button
            type="button"
            className="rag-button rag-button--primary"
            disabled={confirming || preview.file_count === 0}
            onClick={onConfirm}
          >
            {confirming ? "Starting ingest…" : "Start ingest"}
          </button>
          <button
            type="button"
            className="rag-button rag-button--ghost"
            disabled={confirming}
            onClick={onClose}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
