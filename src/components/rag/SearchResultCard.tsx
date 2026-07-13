"use client";

import Link from "next/link";
import { useState } from "react";
import type { SearchHit } from "@/lib/api/search";
import { batchDeleteVaultFiles, reindexVaultFile } from "@/lib/api/vault";
import { VaultStatusBadge } from "@/components/rag/VaultStatusBadge";
import type { VaultIndexStatus } from "@/lib/api/vault";

export function SearchResultCard({
  hit,
  rank,
  onChanged,
}: {
  hit: SearchHit;
  rank: number;
  onChanged?: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const path = hit.relative_path || hit.parent_path;
  const status = hit.index_status as VaultIndexStatus | null | undefined;
  const showStale =
    status === "modified" || status === "not_indexed" || status === "error";

  async function onReindex() {
    if (!hit.file_id) return;
    setBusy(true);
    setError(null);
    try {
      await reindexVaultFile(hit.file_id);
      onChanged?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Reindex failed");
    } finally {
      setBusy(false);
    }
  }

  async function onDelete() {
    if (!hit.file_id) return;
    if (!window.confirm(`Delete ${path}?`)) return;
    setBusy(true);
    setError(null);
    try {
      const result = await batchDeleteVaultFiles([hit.file_id]);
      if (!result.results[0]?.ok) {
        throw new Error(result.results[0]?.error || "Delete failed");
      }
      onChanged?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="rag-result-card">
      <header>
        <strong>#{rank}</strong> · {path || "unknown"} · chunk {hit.chunk_index}
        {status && (
          <span style={{ marginLeft: "0.5rem" }}>
            <VaultStatusBadge status={status} />
          </span>
        )}
      </header>
      {showStale && (
        <p className="rag-muted" title="Index may be stale — Rescan or Reindex">
          Parent file status is {status}; search chunks may be stale until Rescan/Reindex.
        </p>
      )}
      {hit.header_path && (
        <p className="rag-muted">Section: {hit.header_path}</p>
      )}
      <p>{hit.content_preview}</p>
      {hit.parent_content && (
        <details className="rag-parent-context">
          <summary>Parent section context</summary>
          <pre className="rag-parent-preview">{hit.parent_content.slice(0, 1200)}</pre>
        </details>
      )}
      <div>
        vector {(hit.vector_score ?? hit.display_score).toFixed(3)}
        <span className="rag-muted"> · final {hit.final_score.toFixed(3)}</span>
      </div>
      <div className="rag-score-bar" aria-hidden="true">
        <div
          className="rag-score-fill"
          style={{
            width: `${Math.min(100, Math.max(0, (hit.vector_score ?? hit.display_score) * 100))}%`,
          }}
        />
      </div>
      {hit.file_id && (
        <div style={{ display: "flex", gap: "0.75rem", marginTop: "0.5rem" }}>
          <Link
            href={`/rag/library/edit/${path.split("/").map(encodeURIComponent).join("/")}`}
            className="cp-link"
          >
            Open
          </Link>
          <button type="button" className="cp-link" disabled={busy} onClick={onReindex}>
            Reindex
          </button>
          <button type="button" className="cp-link" disabled={busy} onClick={onDelete}>
            Delete
          </button>
        </div>
      )}
      {error && <div className="rag-error">{error}</div>}
    </article>
  );
}
