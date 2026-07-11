import type { Category, FileListItem } from "@/lib/api/files";
import { CATEGORY_LABELS } from "@/lib/api/files";
import Link from "next/link";
import { IngestStatusBadge } from "./IngestStatusBadge";

export function LibraryFilters({
  category,
  keyword,
  date,
  onCategoryChange,
  onKeywordChange,
  onDateChange,
  onFilter,
}: {
  category: Category | "";
  keyword: string;
  date: string;
  onCategoryChange: (value: Category | "") => void;
  onKeywordChange: (value: string) => void;
  onDateChange: (value: string) => void;
  onFilter: () => void;
}) {
  return (
    <div className="rag-panel">
      <label htmlFor="lib-category">Category </label>
      <select
        id="lib-category"
        className="rag-select"
        value={category}
        onChange={(e) => onCategoryChange(e.target.value as Category | "")}
      >
        <option value="">All</option>
        <option value="RND">RND</option>
        <option value="Daily">Daily</option>
        <option value="case">case</option>
      </select>
      <label htmlFor="lib-keyword" style={{ marginTop: "0.5rem", display: "block" }}>
        Keyword
      </label>
      <input
        id="lib-keyword"
        className="rag-input"
        placeholder="Keyword filter"
        value={keyword}
        onChange={(e) => onKeywordChange(e.target.value)}
      />
      <label htmlFor="lib-date" style={{ marginTop: "0.5rem", display: "block" }}>
        Date (YYYY-MM-DD)
      </label>
      <input
        id="lib-date"
        className="rag-input"
        type="date"
        value={date}
        onChange={(e) => onDateChange(e.target.value)}
      />
      <button type="button" className="rag-button" onClick={onFilter} style={{ marginTop: "0.5rem" }}>
        Filter
      </button>
      <Link href="/rag/library/create" className="cp-link" style={{ marginLeft: "0.5rem" }}>
        Create
      </Link>
    </div>
  );
}

export function LibraryList({
  files,
  onReindex,
}: {
  files: FileListItem[];
  onReindex: (path: string) => void;
}) {
  if (files.length === 0) {
    return <p>No documents indexed yet — create one</p>;
  }
  return (
    <ul className="rag-library-list" style={{ listStyle: "none", padding: 0 }}>
      {files.map((f) => (
        <li key={f.path} className="rag-result-card">
          <div>
            <strong>{f.name}</strong> · {CATEGORY_LABELS[f.category]}
          </div>
          <div>
            <IngestStatusBadge status={f.index_status} /> · chunks {f.chunk_count ?? 0}
          </div>
          <div style={{ marginTop: "0.5rem" }}>
            <Link
              href={`/rag/library/edit/${f.path.split("/").map(encodeURIComponent).join("/")}`}
              className="cp-link"
            >
              Edit
            </Link>
            <button
              type="button"
              className="rag-button"
              style={{ marginLeft: "0.5rem" }}
              onClick={() => onReindex(f.path)}
            >
              Re-index
            </button>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function LibrarySkeleton() {
  return (
    <div className="rag-skeleton-list" aria-busy="true" aria-label="Loading library">
      {[1, 2, 3, 4].map((i) => (
        <div key={i} className="rag-skeleton-card rag-skeleton-card-tall" />
      ))}
    </div>
  );
}
