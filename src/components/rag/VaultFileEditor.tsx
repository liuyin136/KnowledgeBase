"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  getVaultFileByPath,
  getVaultFileContent,
  languageFromPath,
  saveVaultFileContent,
  type VaultFile,
} from "@/lib/api/vault";
import { pollJobUntilDone } from "@/lib/api/jobs";
import type { IngestPhase, IngestPhaseName } from "@/lib/api/ingest";
import { IngestWorkflowLog } from "@/components/rag/IngestWorkflowLog";
import { VaultMarkdownPreview } from "@/components/rag/VaultMarkdownPreview";
import { VaultStatusBadge } from "@/components/rag/VaultStatusBadge";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), {
  ssr: false,
  loading: () => <p>Loading editor...</p>,
});

type EditorTab = "source" | "preview";

export function VaultFileEditor({ relativePath }: { relativePath: string }) {
  const [file, setFile] = useState<VaultFile | null>(null);
  const [content, setContent] = useState("");
  const [savedContent, setSavedContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [tab, setTab] = useState<EditorTab>("source");
  const [ingestLog, setIngestLog] = useState<IngestPhase[] | null>(null);
  const [ingestActivePhase, setIngestActivePhase] = useState<IngestPhaseName | null>(null);
  const [ingesting, setIngesting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const meta = await getVaultFileByPath(relativePath);
      if (!meta) throw new Error("File not found in vault");
      setFile(meta);
      const res = await getVaultFileContent(meta.id);
      setContent(res.content);
      setSavedContent(res.content);
      setDirty(false);
      const locked = meta.ingest_locked || meta.index_status === "pending";
      const readOnly = !meta.mutable || locked;
      setTab(readOnly ? "preview" : "source");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load file");
    } finally {
      setLoading(false);
    }
  }, [relativePath]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleSave() {
    if (!file) return;
    if (!file.mutable || file.ingest_locked) {
      setError("File is locked or not editable");
      return;
    }
    setSaving(true);
    setIngesting(true);
    setIngestLog([]);
    setIngestActivePhase("ast_split");
    setError(null);
    setToast(null);
    try {
      const res = await saveVaultFileContent(file.id, content);
      setSavedContent(content);
      setDirty(false);
      setFile(res.file);
      if (res.ingest_job_id) {
        const job = await pollJobUntilDone(res.ingest_job_id, {
          timeoutMs: 300_000,
          onProgress: (status) => {
            const prog = status.ingest_progress;
            if (prog) {
              setIngestLog(prog.workflow_log);
              setIngestActivePhase(prog.active_phase);
            }
          },
        });
        if (job.status === "failed") {
          throw new Error(job.error || "Ingest job failed");
        }
        const prog = job.ingest_progress;
        if (prog) {
          setIngestLog(prog.workflow_log);
          setIngestActivePhase(null);
        }
      }
      setToast("Saved and re-indexed.");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
      setIngesting(false);
    }
  }

  if (loading) return <p>Loading {relativePath}...</p>;

  const locked = !!(file?.ingest_locked || file?.index_status === "pending");
  const readOnly = !file?.mutable || locked;

  return (
    <>
      <div className="rag-panel">
        <Link href="/rag/library" className="cp-link">
          ← Library
        </Link>
        <div>{relativePath}</div>
        {file && <VaultStatusBadge status={file.index_status} />}
        <button
          type="button"
          className="rag-button"
          onClick={handleSave}
          disabled={saving || !dirty || readOnly}
        >
          {saving ? "Saving..." : readOnly ? "Read-only" : "Save & Re-ingest"}
        </button>
      </div>
      <div className="vault-editor-tabs" role="tablist" aria-label="Editor mode">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "source"}
          className={tab === "source" ? "vault-editor-tab active" : "vault-editor-tab"}
          onClick={() => setTab("source")}
        >
          Source
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "preview"}
          className={tab === "preview" ? "vault-editor-tab active" : "vault-editor-tab"}
          onClick={() => setTab("preview")}
        >
          Preview
        </button>
      </div>
      {error && <div className="rag-error">{error}</div>}
      {toast && <div className="rag-toast">{toast}</div>}
      {(ingesting || (ingestLog && ingestLog.length > 0)) && (
        <IngestWorkflowLog
          workflowLog={ingestLog}
          activePhase={ingestActivePhase}
          loading={ingesting}
          relativePath={relativePath}
        />
      )}
      {tab === "source" ? (
        <div style={{ border: "1px solid var(--cp-border)" }}>
          <MonacoEditor
            height="70vh"
            language={languageFromPath(relativePath)}
            theme="vs-dark"
            value={content}
            onChange={(v) => {
              if (readOnly) return;
              const next = v ?? "";
              setContent(next);
              setDirty(next !== savedContent);
            }}
            options={{ minimap: { enabled: false }, wordWrap: "on", readOnly }}
          />
        </div>
      ) : (
        <div className="vault-preview-panel" style={{ minHeight: "70vh" }}>
          <VaultMarkdownPreview content={content} relativePath={relativePath} />
        </div>
      )}
    </>
  );
}
