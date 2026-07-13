"use client";

import Link from "next/link";
import type { VaultFile } from "@/lib/api/vault";
import { VaultStatusBadge } from "@/components/rag/VaultStatusBadge";

function encodePathSegments(relativePath: string): string {
  return relativePath.split("/").map(encodeURIComponent).join("/");
}

export function VaultFileList({
  files,
  selected,
  onToggle,
  onToggleAll,
  onIngest,
  onClearIndex,
  globalMigrating = false,
  page,
  pageSize,
  total,
  totalPages,
  onPageChange,
  onPageSizeChange,
}: {
  files: VaultFile[];
  selected: Set<string>;
  onToggle: (id: string) => void;
  onToggleAll: () => void;
  onIngest: (id: string) => void;
  onClearIndex: (id: string) => void;
  globalMigrating?: boolean;
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
}) {
  const allSelected = files.length > 0 && files.every((f) => selected.has(f.id));

  return (
    <div className="rag-panel">
      <div style={{ display: "flex", gap: "1rem", alignItems: "center", marginBottom: "0.75rem" }}>
        <label>
          Page size{" "}
          <select
            className="rag-input"
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
          >
            <option value={5}>5</option>
            <option value={10}>10</option>
            <option value={20}>20</option>
          </select>
        </label>
        <span>
          {total} files · page {page}/{Math.max(totalPages, 1)}
        </span>
      </div>

      <table className="vault-table" style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={{ textAlign: "left" }}>
              <input type="checkbox" checked={allSelected} onChange={onToggleAll} />
            </th>
            <th style={{ textAlign: "left" }}>File</th>
            <th style={{ textAlign: "left" }}>Preview</th>
            <th style={{ textAlign: "left" }}>Status</th>
            <th style={{ textAlign: "left" }}>Chunks</th>
            <th style={{ textAlign: "left" }}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {files.map((f) => {
            const locked = f.ingest_locked || f.index_status === "pending" || globalMigrating;
            const canClear =
              !locked && (f.index_status === "indexed" || f.index_status === "error");
            const pathHref = encodePathSegments(f.relative_path);
            return (
              <tr key={f.id} style={{ borderTop: "1px solid var(--cp-border)" }}>
                <td>
                  <input
                    type="checkbox"
                    checked={selected.has(f.id)}
                    onChange={() => onToggle(f.id)}
                    disabled={locked}
                  />
                </td>
                <td>
                  <code>{f.relative_path}</code>
                </td>
                <td>
                  <span className="vault-list-preview" title={f.content_preview ?? undefined}>
                    {f.content_preview ?? "—"}
                  </span>
                </td>
                <td>
                  <VaultStatusBadge status={f.index_status} />
                </td>
                <td>{f.chunk_count}</td>
                <td style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                  <Link href={`/rag/library/view/${pathHref}`} className="cp-link">
                    View
                  </Link>
                  {f.mutable && !locked ? (
                    <Link href={`/rag/library/edit/${pathHref}`} className="cp-link">
                      Edit
                    </Link>
                  ) : null}
                  <button
                    type="button"
                    className="cp-link"
                    disabled={locked}
                    onClick={() => onIngest(f.id)}
                  >
                    Ingest
                  </button>
                  {canClear ? (
                    <button
                      type="button"
                      className="cp-link"
                      onClick={() => onClearIndex(f.id)}
                    >
                      Clear index
                    </button>
                  ) : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem" }}>
        <button
          type="button"
          className="rag-button"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          Prev
        </button>
        <button
          type="button"
          className="rag-button"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
        >
          Next
        </button>
      </div>
    </div>
  );
}
