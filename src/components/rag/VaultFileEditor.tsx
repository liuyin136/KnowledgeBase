"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  getVaultFileByPath,
  getVaultFileContent,
  ingestVaultFile,
  languageFromPath,
  previewIngest,
  saveVaultFileContent,
  type VaultFile,
} from "@/lib/api/vault";
import { pollJobUntilDone } from "@/lib/api/jobs";
import type { IngestPhase, IngestPhaseName } from "@/lib/api/ingest";
import { IngestConfirmDialog } from "@/components/rag/IngestConfirmDialog";
import { IngestProgressModal } from "@/components/rag/IngestProgressModal";
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
  const [progressOpen, setProgressOpen] = useState(false);
  const [ingestConfirmOpen, setIngestConfirmOpen] = useState(false);
  const [ingestPreview, setIngestPreview] = useState<Awaited<
    ReturnType<typeof previewIngest>
  > | null>(null);
  const [confirmingIngest, setConfirmingIngest] = useState(false);

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

  async function pollIngestJob(jobId: string) {
    setIngesting(true);
    setProgressOpen(true);
    setIngestLog([]);
    setIngestActivePhase("front_matter");
    try {
      const job = await pollJobUntilDone(jobId, {
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
      await load();
    } finally {
      setIngesting(false);
    }
  }

  async function handleSave() {
    if (!file) return;
    if (!file.mutable || file.ingest_locked) {
      setError("File is locked or not editable");
      return;
    }
    setSaving(true);
    setError(null);
    setToast(null);
    try {
      const res = await saveVaultFileContent(file.id, content);
      setSavedContent(content);
      setDirty(false);
      setFile(res.file);
      if (res.ingest_job_id) {
        setToast("Saved. Re-indexing after save…");
        await pollIngestJob(res.ingest_job_id);
        setToast("Saved and re-indexed.");
      } else {
        setToast("Saved.");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  async function openIngestConfirm() {
    if (!file) return;
    setError(null);
    const preview = await previewIngest([file.id]);
    setIngestPreview(preview);
    setIngestConfirmOpen(true);
  }

  async function handleConfirmIngest() {
    if (!file) return;
    setConfirmingIngest(true);
    setIngestConfirmOpen(false);
    try {
      const res = await ingestVaultFile(file.id);
      await pollIngestJob(res.ingest_job_id);
      setToast("Ingest complete.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ingest failed");
    } finally {
      setConfirmingIngest(false);
    }
  }

  if (loading) return <p>Loading {relativePath}...</p>;

  const locked = !!(file?.ingest_locked || file?.index_status === "pending");
  const readOnly = !file?.mutable || locked;
  const showIngest =
    file &&
    !locked &&
    (file.index_status === "not_indexed" || file.index_status === "error");
  const indexedSave = file?.index_status === "indexed";

  return (
    <>
      <div className="rag-panel">
        <Link href="/rag/library" className="cp-link">
          ← Library
        </Link>
        <div>{relativePath}</div>
        {file && <VaultStatusBadge status={file.index_status} />}
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <button
            type="button"
            className="rag-button"
            onClick={handleSave}
            disabled={saving || ingesting || !dirty || readOnly}
          >
            {saving ? "Saving..." : readOnly ? "Read-only" : "Save"}
          </button>
          {showIngest ? (
            <button
              type="button"
              className="rag-button"
              disabled={saving || ingesting || confirmingIngest}
              onClick={openIngestConfirm}
            >
              Ingest
            </button>
          ) : null}
        </div>
        {indexedSave && dirty && (
          <p className="rag-muted" style={{ marginTop: "0.5rem" }}>
            Saving an indexed file will automatically re-ingest.
          </p>
        )}
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
      <IngestConfirmDialog
        open={ingestConfirmOpen}
        preview={ingestPreview}
        confirming={confirmingIngest}
        onConfirm={handleConfirmIngest}
        onClose={() => setIngestConfirmOpen(false)}
      />
      <IngestProgressModal
        open={progressOpen}
        title={indexedSave ? "Re-indexing after save" : "Ingest progress"}
        relativePath={relativePath}
        workflowLog={ingestLog}
        activePhase={ingestActivePhase}
        loading={ingesting}
        onClose={() => !ingesting && setProgressOpen(false)}
      />
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
