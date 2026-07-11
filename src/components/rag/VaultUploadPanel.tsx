"use client";

import { useRef, useState } from "react";
import { batchUploadVaultFiles, getBatchStatus } from "@/lib/api/vault";

function summarizeBatch(files: { status: string }[]): string {
  const created = files.filter((f) => f.status === "created").length;
  const replaced = files.filter((f) => f.status === "replaced").length;
  const failed = files.filter((f) => f.status === "failed").length;
  const parts: string[] = [];
  if (created) parts.push(`${created} created`);
  if (replaced) parts.push(`${replaced} replaced`);
  if (failed) parts.push(`${failed} failed`);
  return parts.join(", ") || "done";
}

export function VaultUploadPanel({
  folderId,
  onDone,
}: {
  folderId: string | null;
  onDone: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<string | null>(null);
  const [outcomes, setOutcomes] = useState<
    { filename: string; status: string; error_message?: string | null }[]
  >([]);
  const [filename, setFilename] = useState("note.md");

  async function handleFiles(fileList: FileList | null) {
    if (!folderId) {
      setError("Select a folder first");
      return;
    }
    if (!fileList?.length) return;
    setBusy(true);
    setError(null);
    setProgress(null);
    setOutcomes([]);
    try {
      const files = Array.from(fileList);
      const batch = await batchUploadVaultFiles(folderId, files);
      setOutcomes(
        batch.files.map((f) => ({
          filename: f.filename,
          status: f.status,
          error_message: f.error_message,
        }))
      );
      setProgress(`Batch ${batch.batch_id.slice(0, 8)}… — ${summarizeBatch(batch.files)}`);
      for (let i = 0; i < 60; i++) {
        const status = await getBatchStatus(batch.batch_id);
        const done = status.completed_files + status.failed_files;
        setProgress(
          `Indexing ${done}/${status.total_files} (ok ${status.completed_files}, fail ${status.failed_files}) · ${summarizeBatch(batch.files)}`
        );
        if (done >= status.total_files) break;
        await new Promise((r) => setTimeout(r, 2000));
      }
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function createEmpty() {
    if (!folderId) {
      setError("Select a folder first");
      return;
    }
    setBusy(true);
    setError(null);
    setOutcomes([]);
    try {
      const { createVaultFile } = await import("@/lib/api/vault");
      const res = await createVaultFile({ folder_id: folderId, filename, content: `# ${filename}\n` });
      setOutcomes([
        {
          filename,
          status: res.replaced ? "replaced" : "created",
        },
      ]);
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Create failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rag-panel">
      <h3 style={{ marginTop: 0 }}>Upload / Create</h3>
      {!folderId && <p>Select a folder to upload into.</p>}
      <div
        className="vault-dropzone"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          handleFiles(e.dataTransfer.files);
        }}
        style={{
          border: "1px dashed var(--cp-border)",
          padding: "1rem",
          marginBottom: "0.75rem",
          cursor: folderId ? "pointer" : "not-allowed",
        }}
        onClick={() => folderId && inputRef.current?.click()}
      >
        Drag & drop .md / .txt files here, or click to browse
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".md,.txt,text/plain,text/markdown"
          hidden
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>
      <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
        <input
          className="rag-input"
          value={filename}
          onChange={(e) => setFilename(e.target.value)}
          disabled={busy || !folderId}
        />
        <button
          type="button"
          className="rag-button"
          disabled={busy || !folderId}
          onClick={createEmpty}
        >
          Create empty
        </button>
      </div>
      {outcomes.length > 0 && (
        <ul className="vault-upload-outcomes">
          {outcomes.map((o) => (
            <li key={o.filename}>
              <code>{o.filename}</code> — {o.status}
              {o.error_message ? `: ${o.error_message}` : null}
            </li>
          ))}
        </ul>
      )}
      {progress && <div className="rag-toast">{progress}</div>}
      {error && <div className="rag-error">{error}</div>}
    </div>
  );
}
