"use client";

import { useState } from "react";
import type { VaultFolder } from "@/lib/api/vault";
import { createFolder, deleteFolder } from "@/lib/api/vault";
import { VaultFolderRenameDialog } from "@/components/rag/VaultFolderRenameDialog";

export function VaultFolderTree({
  folders,
  selectedId,
  onSelect,
  onChanged,
}: {
  folders: VaultFolder[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onChanged: () => void;
}) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [renameTarget, setRenameTarget] = useState<VaultFolder | null>(null);

  async function onCreate() {
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await createFolder(name.trim());
      setName("");
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Create failed");
    } finally {
      setBusy(false);
    }
  }

  async function onDelete(folder: VaultFolder) {
    if (folder.file_count > 0) return;
    if (!window.confirm(`Delete empty folder "${folder.name}"?`)) return;
    setBusy(true);
    setError(null);
    try {
      await deleteFolder(folder.id);
      if (selectedId === folder.id) onSelect(null);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rag-panel vault-folder-tree">
      <h3 style={{ marginTop: 0 }}>Folders</h3>
      <button
        type="button"
        className={`rag-button ${selectedId === null ? "rag-button-active" : ""}`}
        onClick={() => onSelect(null)}
        style={{ width: "100%", marginBottom: "0.5rem" }}
      >
        All files
      </button>
      <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {folders.map((f) => (
          <li key={f.id} style={{ marginBottom: "0.4rem" }}>
            <button
              type="button"
              className={`rag-button ${selectedId === f.id ? "rag-button-active" : ""}`}
              onClick={() => onSelect(f.id)}
              style={{ width: "100%" }}
            >
              {f.name}
              {f.file_count > 0 ? ` (${f.file_count})` : ""}
            </button>
            <div style={{ display: "flex", gap: "0.25rem", marginTop: "0.2rem", flexWrap: "wrap" }}>
              <button
                type="button"
                className="cp-link"
                disabled={busy}
                onClick={() => setRenameTarget(f)}
              >
                Rename
              </button>
              <button
                type="button"
                className="cp-link"
                disabled={busy || f.file_count > 0}
                title={
                  f.file_count > 0
                    ? `Delete files first (${f.file_count} file(s))`
                    : "Delete empty folder"
                }
                onClick={() => onDelete(f)}
              >
                Delete
              </button>
              {f.file_count > 0 && (
                <span style={{ fontSize: "0.75rem", opacity: 0.75 }}>
                  Delete files first ({f.file_count})
                </span>
              )}
            </div>
          </li>
        ))}
      </ul>
      <div style={{ marginTop: "1rem", display: "flex", gap: "0.5rem" }}>
        <input
          className="rag-input"
          placeholder="New folder"
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={busy}
        />
        <button type="button" className="rag-button" onClick={onCreate} disabled={busy}>
          Add
        </button>
      </div>
      {error && <div className="rag-error">{error}</div>}
      {renameTarget && (
        <VaultFolderRenameDialog
          folder={renameTarget}
          open={!!renameTarget}
          onClose={() => setRenameTarget(null)}
          onRenamed={onChanged}
        />
      )}
    </div>
  );
}
