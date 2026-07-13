"use client";

import type { RerankPreviewMeta } from "@/lib/api/search";

export function RerankConfirmDialog({
  open,
  preview,
  confirming,
  onConfirm,
  onSkip,
  onClose,
}: {
  open: boolean;
  preview: RerankPreviewMeta | null;
  confirming: boolean;
  onConfirm: () => void;
  onSkip: () => void;
  onClose: () => void;
}) {
  if (!open || !preview) return null;

  const softGate = 8192;
  const overSoftGate = preview.rerank_token_count > softGate;
  const overLimit = preview.rerank_token_count > preview.rerank_ctx_limit;
  const ratio = Math.min(
    100,
    (preview.rerank_token_count / Math.max(preview.rerank_ctx_limit, 1)) * 100
  );

  return (
    <div
      className="rag-modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="rerank-confirm-title"
      onClick={onClose}
    >
      <div className="rag-modal rag-rerank-confirm" onClick={(e) => e.stopPropagation()}>
        <h3 id="rerank-confirm-title" style={{ marginTop: 0 }}>
          Confirm rerank
        </h3>
        <p className="rag-rerank-confirm-lead">
          Hierarchical fusion complete. Optional W5 rerank scores grandchild passages against the
          query. Skip to keep hierarchical fusion ranking.
        </p>

        <dl className="rag-rerank-confirm-stats">
          <div>
            <dt>Actual prompt tokens</dt>
            <dd className="rag-rerank-confirm-tokens">
              {preview.rerank_token_count.toLocaleString()}
            </dd>
          </div>
          <div>
            <dt>Soft gate / hard limit</dt>
            <dd>
              {softGate.toLocaleString()} / {preview.rerank_ctx_limit.toLocaleString()}
            </dd>
          </div>
          <div>
            <dt>Passages</dt>
            <dd>
              {preview.rerank_doc_count} / top {preview.rerank_k}
            </dd>
          </div>
        </dl>

        <div className="rag-rerank-confirm-bar" aria-hidden="true">
          <div
            className={`rag-rerank-confirm-fill${overLimit || overSoftGate ? " rag-rerank-confirm-fill--over" : ""}`}
            style={{ width: `${ratio}%` }}
          />
        </div>

        {overSoftGate && (
          <p className="rag-error rag-rerank-confirm-warn">
            Token count exceeds the 8192 soft gate for grandchild+query rerank. Skipping uses
            hierarchical fusion ranking as the final order.
          </p>
        )}
        {overLimit && (
          <p className="rag-error rag-rerank-confirm-warn">
            Token count exceeds reranker context limit. Rerank may fail or OOM on 8GB GPU.
          </p>
        )}

        <div className="rag-rerank-confirm-actions">
          <button
            type="button"
            className="rag-button rag-button--primary"
            disabled={confirming}
            onClick={onConfirm}
          >
            {confirming ? "Starting rerank…" : "Run rerank"}
          </button>
          <button
            type="button"
            className="rag-button"
            disabled={confirming}
            onClick={onSkip}
          >
            Use fusion ranking only
          </button>
          <button type="button" className="rag-button rag-button--ghost" disabled={confirming} onClick={onClose}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
