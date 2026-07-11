import type { IndexStatus } from "@/lib/api/files";

const LABELS: Record<IndexStatus, string> = {
  pending: "Pending",
  indexed: "Indexed",
  error: "Error",
  not_indexed: "Not indexed",
};

export function IngestStatusBadge({ status }: { status?: IndexStatus }) {
  const value = status ?? "not_indexed";
  return <span className={`rag-badge rag-badge-${value}`}>{LABELS[value]}</span>;
}
