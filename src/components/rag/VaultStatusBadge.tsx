"use client";

import type { VaultIndexStatus } from "@/lib/api/vault";

const LABELS: Record<VaultIndexStatus, string> = {
  not_indexed: "not indexed",
  pending: "pending",
  indexed: "indexed",
  modified: "modified",
  error: "error",
  deleted: "deleted",
};

export function VaultStatusBadge({ status }: { status: VaultIndexStatus }) {
  const cls =
    status === "indexed"
      ? "rag-badge-indexed"
      : status === "pending"
        ? "rag-badge-pending"
        : status === "error"
          ? "rag-badge-error"
          : status === "modified"
            ? "rag-badge-modified"
            : "rag-badge-not_indexed";
  return <span className={`rag-badge ${cls}`}>{LABELS[status] ?? status}</span>;
}
