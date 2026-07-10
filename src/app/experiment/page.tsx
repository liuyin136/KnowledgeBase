"use client";

import { useCallback, useEffect, useState } from "react";
import {
  CATEGORY_LABELS,
  type Category,
  type FileListItem,
  listFiles,
} from "@/lib/api/files";
import { FileFilters } from "@/components/experiment/FileFilters";
import { FileList } from "@/components/experiment/FileList";

export default function ExperimentPage() {
  const [category, setCategory] = useState<Category | "">("");
  const [keyword, setKeyword] = useState("");
  const [date, setDate] = useState("");
  const [files, setFiles] = useState<FileListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadFiles = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listFiles({
        category: category || undefined,
        keyword: keyword || undefined,
        date: date || undefined,
      });
      setFiles(res.files);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load files");
    } finally {
      setLoading(false);
    }
  }, [category, keyword, date]);

  useEffect(() => {
    loadFiles();
  }, [loadFiles]);

  return (
    <>
      <FileFilters
        category={category}
        keyword={keyword}
        date={date}
        onCategoryChange={setCategory}
        onKeywordChange={setKeyword}
        onDateChange={setDate}
        onSearch={loadFiles}
      />
      {error && <div className="cp-error">{error}</div>}
      {loading ? (
        <p className="cp-status">Scanning data vault...</p>
      ) : (
        <FileList files={files} categoryLabels={CATEGORY_LABELS} />
      )}
    </>
  );
}
