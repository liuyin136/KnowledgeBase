"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { getFileContent, languageFromPath, saveFileContent } from "@/lib/api/files";
import { pollJobUntilDone } from "@/lib/api/jobs";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), {
  ssr: false,
  loading: () => <p>Loading editor...</p>,
});

export function LogEditor({ filePath }: { filePath: string }) {
  const [content, setContent] = useState("");
  const [savedContent, setSavedContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getFileContent(filePath);
      setContent(res.content);
      setSavedContent(res.content);
      setDirty(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load file");
    } finally {
      setLoading(false);
    }
  }, [filePath]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleSave() {
    setSaving(true);
    setError(null);
    setToast(null);
    try {
      const res = await saveFileContent(filePath, content);
      setSavedContent(content);
      setDirty(false);
      if (res.ingest_job_id) {
        const job = await pollJobUntilDone(res.ingest_job_id, { timeoutMs: 300_000 });
        if (job.status === "failed") {
          throw new Error(job.error || "Ingest job failed");
        }
      }
      setToast("Saved and re-indexed.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <p>Loading {filePath}...</p>;

  return (
    <>
      <div className="rag-panel">
        <Link href="/rag/library" className="cp-link">
          ← Library
        </Link>
        <div>{filePath}</div>
        <button type="button" className="rag-button" onClick={handleSave} disabled={saving || !dirty}>
          {saving ? "Saving..." : "Save & Re-ingest"}
        </button>
      </div>
      {error && <div className="rag-error">{error}</div>}
      {toast && <div className="rag-toast">{toast}</div>}
      <div style={{ border: "1px solid var(--cp-border)" }}>
        <MonacoEditor
          height="70vh"
          language={languageFromPath(filePath)}
          theme="vs-dark"
          value={content}
          onChange={(v) => {
            const next = v ?? "";
            setContent(next);
            setDirty(next !== savedContent);
          }}
          options={{ minimap: { enabled: false }, wordWrap: "on" }}
        />
      </div>
    </>
  );
}
