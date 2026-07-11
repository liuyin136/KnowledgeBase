"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function VaultMarkdownPreview({
  content,
  relativePath,
}: {
  content: string;
  relativePath: string;
}) {
  const isMarkdown = relativePath.endsWith(".md");

  if (!isMarkdown) {
    return (
      <pre className="vault-preview vault-preview-plain">{content || "(empty)"}</pre>
    );
  }

  return (
    <div className="vault-preview vault-preview-md">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content || "(empty)"}</ReactMarkdown>
    </div>
  );
}
