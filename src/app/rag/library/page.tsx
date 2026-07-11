"use client";

import { useCallback, useEffect, useState } from "react";
import {
  batchDeleteVaultFiles,
  listFolders,
  listVaultFiles,
  reindexVaultFile,
  syncVault,
  type VaultFile,
  type VaultFolder,
} from "@/lib/api/vault";
import { VaultFolderTree } from "@/components/rag/VaultFolderTree";
import { VaultFileList } from "@/components/rag/VaultFileList";
import { VaultUploadPanel } from "@/components/rag/VaultUploadPanel";
import { pollJobUntilDone } from "@/lib/api/jobs";
import type { IngestPhase, IngestPhaseName } from "@/lib/api/ingest";
import { IngestWorkflowLog } from "@/components/rag/IngestWorkflowLog";
import { LibrarySkeleton } from "@/components/rag/LibraryList";

export default function RagLibraryPage() {
  const [folders, setFolders] = useState<VaultFolder[]>([]);
  const [folderId, setFolderId] = useState<string | null>(null);
  const [keyword, setKeyword] = useState("");
  const [files, setFiles] = useState<VaultFile[]>([]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [ingestLog, setIngestLog] = useState<IngestPhase[] | null>(null);
  const [ingestActivePhase, setIngestActivePhase] = useState<IngestPhaseName | null>(null);
  const [ingesting, setIngesting] = useState(false);

  const loadFolders = useCallback(async () => {
    const list = await listFolders();
    setFolders(list);
  }, []);

  const loadFiles = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listVaultFiles({
        folder_id: folderId || undefined,
        keyword: keyword || undefined,
        page,
        page_size: pageSize,
      });
      setFiles(res.files);
      setTotal(res.total);
      setTotalPages(res.total_pages);
      setSelected(new Set());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load vault");
    } finally {
      setLoading(false);
    }
  }, [folderId, keyword, page, pageSize]);

  useEffect(() => {
    loadFolders().catch((e) => setError(e instanceof Error ? e.message : "Failed"));
  }, [loadFolders]);

  useEffect(() => {
    loadFiles();
  }, [loadFiles]);

  async function onRescan() {
    setToast(null);
    setError(null);
    try {
      const report = await syncVault();
      setToast(
        `Rescan: scanned ${report.files_scanned}, +${report.drift_added} ~${report.drift_modified} -${report.drift_removed}`
      );
      await loadFolders();
      await loadFiles();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Rescan failed");
    }
  }

  async function onBulkDelete() {
    if (selected.size === 0) return;
    if (!window.confirm(
      `Delete ${selected.size} file(s)? This removes the file on disk, SQLite metadata, and Neo4j index.`
    )) return;
    setError(null);
    try {
      const result = await batchDeleteVaultFiles([...selected]);
      const failed = result.results.filter((r) => !r.ok);
      if (failed.length) {
        setError(`Some deletes failed: ${failed.map((f) => f.error).join("; ")}`);
      }
      await loadFiles();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  async function onReindex(id: string) {
    setIngesting(true);
    setIngestLog([]);
    setIngestActivePhase("ast_split");
    setError(null);
    try {
      const res = await reindexVaultFile(id);
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
          throw new Error(job.error || "Reindex failed");
        }
      }
      setToast("Reindex complete.");
      await loadFiles();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Reindex failed");
    } finally {
      setIngesting(false);
      setIngestActivePhase(null);
    }
  }

  return (
    <>
      <div className="rag-banner" style={{ marginBottom: "1rem" }}>
        Manage files through RAG Library only. Direct changes under{" "}
        <code>/data/rag/vault/</code> are unsupported; use Rescan to reconcile.
      </div>

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem", flexWrap: "wrap" }}>
        <button type="button" className="rag-button" onClick={onRescan}>
          Rescan
        </button>
        <button
          type="button"
          className="rag-button"
          disabled={selected.size === 0}
          onClick={onBulkDelete}
        >
          Delete selected ({selected.size})
        </button>
        <input
          className="rag-input"
          placeholder="Filter filename"
          value={keyword}
          onChange={(e) => {
            setPage(1);
            setKeyword(e.target.value);
          }}
        />
      </div>

      {toast && <div className="rag-toast">{toast}</div>}
      {error && <div className="rag-error">{error}</div>}
      {(ingesting || (ingestLog && ingestLog.length > 0)) && (
        <IngestWorkflowLog
          workflowLog={ingestLog}
          activePhase={ingestActivePhase}
          loading={ingesting}
        />
      )}

      <div
        className="vault-library-grid"
        style={{
          display: "grid",
          gridTemplateColumns: "240px 1fr",
          gap: "1rem",
          alignItems: "start",
        }}
      >
        <div>
          <VaultFolderTree
            folders={folders}
            selectedId={folderId}
            onSelect={(id) => {
              setPage(1);
              setFolderId(id);
            }}
            onChanged={() => {
              loadFolders();
              loadFiles();
            }}
          />
          <VaultUploadPanel
            folderId={folderId}
            onDone={() => {
              loadFolders();
              loadFiles();
            }}
          />
        </div>

        <div>
          {loading ? (
            <LibrarySkeleton />
          ) : (
            <VaultFileList
              files={files}
              selected={selected}
              onToggle={(id) => {
                const next = new Set(selected);
                if (next.has(id)) next.delete(id);
                else next.add(id);
                setSelected(next);
              }}
              onToggleAll={() => {
                if (files.every((f) => selected.has(f.id))) {
                  setSelected(new Set());
                } else {
                  setSelected(new Set(files.map((f) => f.id)));
                }
              }}
              onReindex={onReindex}
              page={page}
              pageSize={pageSize}
              total={total}
              totalPages={totalPages}
              onPageChange={setPage}
              onPageSizeChange={(size) => {
                setPage(1);
                setPageSize(size);
              }}
            />
          )}
        </div>
      </div>
    </>
  );
}
