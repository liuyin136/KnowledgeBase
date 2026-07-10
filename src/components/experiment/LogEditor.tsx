"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  getFileContent,
  languageFromPath,
  saveFileContent,
} from "@/lib/api/files";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), {
  ssr: false,
  loading: () => <p className="cp-status">Loading editor...</p>,
});

interface LogEditorProps {
  filePath: string;
}

export function LogEditor({ filePath }: LogEditorProps) {
  const [content, setContent] = useState("");
  const [savedContent, setSavedContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("");
  const [dirty, setDirty] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getFileContent(filePath);
      setContent(res.content);
      setSavedContent(res.content);
      setDirty(false);
      setStatus("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load file");
    } finally {
      setLoading(false);
    }
  }, [filePath]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (dirty) {
        e.preventDefault();
      }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  const handleChange = (value: string | undefined) => {
    const next = value ?? "";
    setContent(next);
    const isDirty = next !== savedContent;
    setDirty(isDirty);
    setStatus(isDirty ? "Unsaved changes" : "");
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      await saveFileContent(filePath, content);
      setSavedContent(content);
      setDirty(false);
      setStatus("Saved");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    setContent(savedContent);
    setDirty(false);
    setStatus("Reset to last saved version");
  };

  if (loading) {
    return <p className="cp-status">Loading {filePath}...</p>;
  }

  return (
    <>
      <div className="cp-editor-toolbar">
        <div>
          <Link href="/experiment" className="cp-link">
            ← Back
          </Link>
          <div className="cp-editor-path">{filePath}</div>
        </div>
        <div className="cp-actions" style={{ marginTop: 0 }}>
          <button
            type="button"
            className="cp-btn cp-btn-primary"
            onClick={handleSave}
            disabled={saving || !dirty}
          >
            {saving ? "Saving..." : "Save"}
          </button>
          <button type="button" className="cp-btn" onClick={handleReset}>
            Reset
          </button>
        </div>
      </div>

      {error && <div className="cp-error">{error}</div>}
      {status && (
        <p className={`cp-status${status === "Saved" ? " saved" : ""}`}>{status}</p>
      )}

      <div className="cp-editor-wrap">
        <MonacoEditor
          height="70vh"
          language={languageFromPath(filePath)}
          theme="vs-dark"
          value={content}
          onChange={handleChange}
          options={{
            minimap: { enabled: false },
            fontSize: 14,
            wordWrap: "on",
            scrollBeyondLastLine: false,
          }}
        />
      </div>
    </>
  );
}
