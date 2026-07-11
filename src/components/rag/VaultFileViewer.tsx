"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  getVaultFileByPath,
  getVaultFileContent,
  type VaultFile,
} from "@/lib/api/vault";
import { VaultMarkdownPreview } from "@/components/rag/VaultMarkdownPreview";
import { VaultStatusBadge } from "@/components/rag/VaultStatusBadge";

function encodePathSegments(relativePath: string): string {
  return relativePath.split("/").map(encodeURIComponent).join("/");
}

export function VaultFileViewer({ relativePath }: { relativePath: string }) {
  const [file, setFile] = useState<VaultFile | null>(null);
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const meta = await getVaultFileByPath(relativePath);
      if (!meta) throw new Error("File not found in vault");
      setFile(meta);
      const res = await getVaultFileContent(meta.id);
      setContent(res.content);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load file");
    } finally {
      setLoading(false);
    }
  }, [relativePath]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <p>Loading {relativePath}...</p>;
  if (error) return <div className="rag-error">{error}</div>;

  const locked = !!(file?.ingest_locked || file?.index_status === "pending");
  const canEdit = !!(file?.mutable && !locked);

  return (
    <>
      <div className="rag-panel">
        <Link href="/rag/library" className="cp-link">
          ← Library
        </Link>
        <div>{relativePath}</div>
        {file && <VaultStatusBadge status={file.index_status} />}
        {canEdit && (
          <Link
            href={`/rag/library/edit/${encodePathSegments(relativePath)}`}
            className="rag-button"
            style={{ display: "inline-block", textDecoration: "none" }}
          >
            Edit
          </Link>
        )}
      </div>
      <div className="vault-preview-panel">
        <VaultMarkdownPreview content={content} relativePath={relativePath} />
      </div>
    </>
  );
}
