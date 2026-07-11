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
          Confirm rerank (experiment)
        </h3>
        <p className="rag-rerank-confirm-lead">
          Fusion complete. Rerank will run one forward pass over all shortlisted passages in a
          single prompt.
        </p>

        <dl className="rag-rerank-confirm-stats">
          <div>
            <dt>Actual prompt tokens</dt>
            <dd className="rag-rerank-confirm-tokens">
              {preview.rerank_token_count.toLocaleString()}
            </dd>
          </div>
          <div>
            <dt>Reranker limit</dt>
            <dd>{preview.rerank_ctx_limit.toLocaleString()}</dd>
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
            className={`rag-rerank-confirm-fill${overLimit ? " rag-rerank-confirm-fill--over" : ""}`}
            style={{ width: `${ratio}%` }}
          />
        </div>

        {overLimit && (
          <p className="rag-error rag-rerank-confirm-warn">
            Token count exceeds reranker context limit. Rerank may fail or OOM on 8GB GPU.
          </p>
        )}
        <p className="rag-muted rag-rerank-confirm-disclaimer">
          Experimental: n_ctx=131072 pre-allocates large KV cache. Monitor VRAM in workflow log.
        </p>

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
            Use fusion results only
          </button>
          <button type="button" className="rag-button rag-button--ghost" disabled={confirming} onClick={onClose}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
