"use client";

import type { Category } from "@/lib/api/files";

interface FileFiltersProps {
  category: Category | "";
  keyword: string;
  date: string;
  onCategoryChange: (v: Category | "") => void;
  onKeywordChange: (v: string) => void;
  onDateChange: (v: string) => void;
  onSearch: () => void;
}

export function FileFilters({
  category,
  keyword,
  date,
  onCategoryChange,
  onKeywordChange,
  onDateChange,
  onSearch,
}: FileFiltersProps) {
  return (
    <div className="cp-card">
      <div className="cp-filters">
        <div className="cp-field">
          <label className="cp-label" htmlFor="filter-category">
            Category
          </label>
          <select
            id="filter-category"
            className="cp-select"
            value={category}
            onChange={(e) => onCategoryChange(e.target.value as Category | "")}
          >
            <option value="">All</option>
            <option value="RND">R&D Log</option>
            <option value="Daily">Daily Dev Log</option>
            <option value="case">Troubleshooting Log</option>
          </select>
        </div>
        <div className="cp-field">
          <label className="cp-label" htmlFor="filter-keyword">
            Keyword
          </label>
          <input
            id="filter-keyword"
            className="cp-input"
            type="text"
            placeholder="Search filename or content..."
            value={keyword}
            onChange={(e) => onKeywordChange(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onSearch()}
          />
        </div>
        <div className="cp-field">
          <label className="cp-label" htmlFor="filter-date">
            Date
          </label>
          <input
            id="filter-date"
            className="cp-input"
            type="date"
            value={date}
            onChange={(e) => onDateChange(e.target.value)}
          />
        </div>
      </div>
      <button type="button" className="cp-btn" onClick={onSearch}>
        Search
      </button>
    </div>
  );
}
