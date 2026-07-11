"use client";

export function SearchPanel({
  query,
  loading,
  onQueryChange,
  onSubmit,
  children,
}: {
  query: string;
  loading: boolean;
  onQueryChange: (value: string) => void;
  onSubmit: (e: React.FormEvent) => void;
  children?: React.ReactNode;
}) {
  return (
    <form onSubmit={onSubmit} className="rag-panel">
      <label htmlFor="search-query">Query</label>
      <input
        id="search-query"
        className="rag-input"
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        placeholder="Enter search query..."
        required
        minLength={2}
      />
      {children}
      <button type="submit" className="rag-button" disabled={loading} style={{ marginTop: "1rem" }}>
        {loading ? "Searching..." : "Search"}
      </button>
    </form>
  );
}

export function SearchSkeleton() {
  return (
    <div className="rag-skeleton-list" aria-busy="true" aria-label="Loading search results">
      {[1, 2, 3].map((i) => (
        <div key={i} className="rag-skeleton-card" />
      ))}
    </div>
  );
}
