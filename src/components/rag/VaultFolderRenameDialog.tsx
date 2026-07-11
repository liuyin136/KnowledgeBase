"use client";

import { useEffect, useState } from "react";
import {
  previewFolderRename,
  renameFolder,
  type FolderRenamePreview,
  type VaultFolder,
} from "@/lib/api/vault";
import { VaultStatusBadge } from "@/components/rag/VaultStatusBadge";

export function VaultFolderRenameDialog({
  folder,
  open,
  onClose,
  onRenamed,
}: {
  folder: VaultFolder;
  open: boolean;
  onClose: () => void;
  onRenamed: () => void;
}) {
  const [name, setName] = useState(folder.name);
  const [preview, setPreview] = useState<FolderRenamePreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setName(folder.name);
    setPreview(null);
    setError(null);
  }, [open, folder.id, folder.name]);

  useEffect(() => {
    if (!open || !name.trim() || name.trim() === folder.name) {
      setPreview(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    previewFolderRename(folder.id, name.trim())
      .then((p) => {
        if (!cancelled) setPreview(p);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Preview failed");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, folder.id, folder.name, name]);

  async function onConfirm() {
    if (!preview?.can_rename) return;
    setConfirming(true);
    setError(null);
    try {
      await renameFolder(folder.id, name.trim());
      onRenamed();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Rename failed");
    } finally {
      setConfirming(false);
    }
  }

  if (!open) return null;

  const showPreview = name.trim() !== folder.name;

  return (
    <div
      className="rag-modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="vault-rename-title"
      onClick={onClose}
    >
      <div className="rag-modal" onClick={(e) => e.stopPropagation()}>
        <h3 id="vault-rename-title" style={{ marginTop: 0 }}>
          Rename folder &quot;{folder.name}&quot;
        </h3>
        <label>
          New name
          <input
            className="rag-input"
            style={{ display: "block", width: "100%", marginTop: "0.25rem" }}
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={confirming}
          />
        </label>

        {loading && <p>Loading preview…</p>}

        {showPreview && preview && (
          <div style={{ marginTop: "1rem" }}>
            <p>
              Slug: <code>{preview.old_slug}</code> → <code>{preview.new_slug}</code>
            </p>
            <p>
              {preview.total_files} file(s) in SQLite; {preview.neo4j_knowledge_count} Neo4j
              Knowledge node(s) will update category and path.
            </p>
            {preview.preview_files.length > 0 && (
              <table className="rag-table" style={{ width: "100%", fontSize: "0.85rem" }}>
                <thead>
                  <tr>
                    <th>Old path</th>
                    <th>New path</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.preview_files.map((f) => (
                    <tr key={f.old_relative_path}>
                      <td>
                        <code>{f.old_relative_path}</code>
                      </td>
                      <td>
                        <code>{f.new_relative_path}</code>
                      </td>
                      <td>
                        <VaultStatusBadge status={f.index_status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {preview.has_more_files && (
              <p style={{ marginTop: "0.5rem", opacity: 0.8 }}>
                …and {preview.total_files - preview.preview_files.length} more file(s).
              </p>
            )}
            {!preview.can_rename && preview.block_reason && (
              <div className="rag-error">{preview.block_reason}</div>
            )}
          </div>
        )}

        {error && <div className="rag-error">{error}</div>}

        <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem", justifyContent: "flex-end" }}>
          <button type="button" className="rag-button" onClick={onClose} disabled={confirming}>
            Cancel
          </button>
          <button
            type="button"
            className="rag-button"
            onClick={onConfirm}
            disabled={
              confirming ||
              !showPreview ||
              !preview?.can_rename ||
              loading ||
              name.trim() === folder.name
            }
          >
            {confirming ? "Renaming…" : "Confirm rename"}
          </button>
        </div>
      </div>
    </div>
  );
}
