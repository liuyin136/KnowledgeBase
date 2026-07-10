"use client";

import Link from "next/link";
import type { Category, FileListItem } from "@/lib/api/files";

interface FileListProps {
  files: FileListItem[];
  categoryLabels: Record<Category, string>;
}

function formatDate(ts: number): string {
  return new Date(ts * 1000).toLocaleString();
}

export function FileList({ files, categoryLabels }: FileListProps) {
  if (files.length === 0) {
    return <p className="cp-empty">No logs found. Create one to get started.</p>;
  }

  return (
    <ul className="cp-file-list">
      {files.map((file) => (
        <li key={file.path} className="cp-file-item">
          <div className="cp-file-meta">
            <span className="cp-badge">{categoryLabels[file.category]}</span>
            <span className="cp-file-name">{file.name}</span>
            <div className="cp-file-sub">
              {file.path} · modified {formatDate(file.modified_at)}
            </div>
          </div>
          <Link
            href={`/experiment/edit/${file.path.split("/").map(encodeURIComponent).join("/")}`}
            className="cp-btn"
          >
            View
          </Link>
        </li>
      ))}
    </ul>
  );
}
