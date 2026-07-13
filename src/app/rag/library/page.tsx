"use client";

import { useCallback, useEffect, useState } from "react";
import {
  batchDeleteVaultFiles,
  batchIngestVaultFiles,
  clearVaultIndex,
  getBatchStatus,
  ingestVaultFile,
  listFolders,
  listVaultFiles,
  migrateVaultV16,
  previewIngest,
  syncVault,
  type VaultFile,
  type VaultFolder,
} from "@/lib/api/vault";
import { pollJobUntilDone } from "@/lib/api/jobs";
import type { IngestPhase, IngestPhaseName } from "@/lib/api/ingest";
import { IngestConfirmDialog } from "@/components/rag/IngestConfirmDialog";
import { IngestProgressModal } from "@/components/rag/IngestProgressModal";
import { VaultFolderTree } from "@/components/rag/VaultFolderTree";
import { VaultFileList } from "@/components/rag/VaultFileList";
import { VaultUploadPanel } from "@/components/rag/VaultUploadPanel";
import { LibrarySkeleton } from "@/components/rag/LibraryList";

function deleteConfirmMessage(selectedFiles: VaultFile[]): string {
  const indexed = selectedFiles.filter(
    (f) => f.index_status === "indexed" || f.index_status === "error"
  ).length;
  const notIndexed = selectedFiles.filter((f) => f.index_status === "not_indexed").length;
  const parts = [`Delete ${selectedFiles.length} file(s)?`];
  if (indexed) {
    parts.push(
      `${indexed} indexed file(s) will also remove their Neo4j index.`
    );
  }
  if (notIndexed) {
    parts.push(
      `${notIndexed} not-indexed file(s) will remove disk + metadata only.`
    );
  }
  return parts.join(" ");
}

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
  const [ingestRelativePath, setIngestRelativePath] = useState<string | null>(null);
  const [ingesting, setIngesting] = useState(false);
  const [progressOpen, setProgressOpen] = useState(false);
  const [migrating, setMigrating] = useState(false);
  const [ingestConfirmOpen, setIngestConfirmOpen] = useState(false);
  const [ingestPreview, setIngestPreview] = useState<Awaited<
    ReturnType<typeof previewIngest>
  > | null>(null);
  const [pendingIngestIds, setPendingIngestIds] = useState<string[]>([]);
  const [confirmingIngest, setConfirmingIngest] = useState(false);

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
        search_content: Boolean(keyword),
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

  async function pollIngestJob(jobId: string, relativePath: string | null) {
    const job = await pollJobUntilDone(jobId, {
      timeoutMs: 600_000,
      onProgress: (status) => {
        const prog = status.ingest_progress;
        if (prog) {
          setIngestLog(prog.workflow_log);
          setIngestActivePhase(prog.active_phase);
          if (prog.relative_path) setIngestRelativePath(prog.relative_path);
        }
      },
    });
    if (job.status === "failed") {
      throw new Error(job.error || `Ingest failed for ${relativePath ?? jobId}`);
    }
    const finalProg = job.ingest_progress;
    if (finalProg) {
      setIngestLog(finalProg.workflow_log);
      setIngestActivePhase(null);
    }
  }

  async function runSequentialIngest(fileIds: string[]) {
    setIngesting(true);
    setProgressOpen(true);
    setIngestLog([]);
    setIngestActivePhase("front_matter");
    setError(null);
    try {
      const batch = await batchIngestVaultFiles(fileIds);
      if (batch.skipped.length) {
        setToast(
          `Skipped ${batch.skipped.length} file(s): ${batch.skipped.map((s) => s.reason).join("; ")}`
        );
      }
      const status = await getBatchStatus(batch.batch_id);
      for (const entry of status.files) {
        if (!entry.job_id) continue;
        const row = files.find((f) => f.id === entry.file_id);
        setIngestRelativePath(row?.relative_path ?? entry.filename);
        setIngestLog([]);
        setIngestActivePhase("front_matter");
        await pollIngestJob(entry.job_id, row?.relative_path ?? entry.filename);
        await loadFiles();
      }
      setToast(`Ingest complete for ${batch.queued.length} file(s).`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ingest failed");
    } finally {
      setIngesting(false);
    }
  }

  async function openIngestConfirm(ids: string[]) {
    if (!ids.length) return;
    setError(null);
    const preview = await previewIngest(ids);
    setIngestPreview(preview);
    setPendingIngestIds(ids);
    setIngestConfirmOpen(true);
  }

  async function onConfirmIngest() {
    setConfirmingIngest(true);
    setIngestConfirmOpen(false);
    try {
      const ingestible = ingestPreview?.items.filter((i) => i.ingestible).map((i) => i.file_id) ?? [];
      const ids = pendingIngestIds.filter((id) => ingestible.includes(id));
      if (ids.length === 1) {
        setIngesting(true);
        setProgressOpen(true);
        setIngestLog([]);
        setIngestActivePhase("front_matter");
        const res = await ingestVaultFile(ids[0]);
        setIngestRelativePath(res.relative_path);
        await pollIngestJob(res.ingest_job_id, res.relative_path);
        setToast("Ingest complete.");
        await loadFiles();
        setIngesting(false);
      } else {
        await runSequentialIngest(ids);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ingest failed");
      setIngesting(false);
    } finally {
      setConfirmingIngest(false);
      setPendingIngestIds([]);
    }
  }

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
    const selectedFiles = files.filter((f) => selected.has(f.id));
    if (!window.confirm(deleteConfirmMessage(selectedFiles))) return;
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

  async function onClearIndex(id: string) {
    const row = files.find((f) => f.id === id);
    if (!row) return;
    if (
      !window.confirm(
        `Clear index for ${row.relative_path}? The file stays on disk; search will no longer include it until re-ingested.`
      )
    ) {
      return;
    }
    setError(null);
    try {
      await clearVaultIndex(id);
      setToast("Index cleared.");
      await loadFiles();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Clear index failed");
    }
  }

  async function onBulkClearIndex() {
    const indexed = files.filter(
      (f) =>
        selected.has(f.id) &&
        (f.index_status === "indexed" || f.index_status === "error")
    );
    if (!indexed.length) {
      setError("Select indexed file(s) to clear.");
      return;
    }
    if (
      !window.confirm(
        `Clear index for ${indexed.length} file(s)? Files remain on disk; use Ingest to re-index.`
      )
    ) {
      return;
    }
    setError(null);
    let failed = 0;
    for (const f of indexed) {
      try {
        await clearVaultIndex(f.id);
      } catch {
        failed += 1;
      }
    }
    setToast(
      failed
        ? `Cleared ${indexed.length - failed} file(s); ${failed} failed.`
        : `Cleared index for ${indexed.length} file(s).`
    );
    await loadFiles();
  }

  async function onMigrateAll() {
    if (
      !window.confirm(
        "Migrate All will purge Neo4j ingestion data, clear search caches, " +
          "reset vault index status to not_indexed, and resync files. " +
          "You must run bulk Ingest afterward. Continue?"
      )
    ) {
      return;
    }
    setMigrating(true);
    setError(null);
    setToast(null);
    try {
      const migration = await migrateVaultV16();
      setToast(
        `Migration complete: ${migration.total_files} file(s) set to not_indexed. ` +
          "Use Ingest selected to re-index."
      );
      await loadFolders();
      await loadFiles();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Migration failed");
    } finally {
      setMigrating(false);
    }
  }

  const selectedIndexed = files.filter(
    (f) =>
      selected.has(f.id) &&
      (f.index_status === "indexed" || f.index_status === "error")
  ).length;

  return (
    <>
      <div className="rag-banner" style={{ marginBottom: "1rem" }}>
        Manage files through RAG Library only. Direct changes under{" "}
        <code>/data/rag/vault/</code> are unsupported; use Rescan to reconcile.
      </div>

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem", flexWrap: "wrap" }}>
        <button type="button" className="rag-button" onClick={onRescan} disabled={migrating || ingesting}>
          Rescan
        </button>
        <button
          type="button"
          className="rag-button"
          disabled={migrating || ingesting}
          onClick={onMigrateAll}
        >
          Migrate All
        </button>
        <button
          type="button"
          className="rag-button"
          disabled={selected.size === 0 || migrating || ingesting}
          onClick={() => openIngestConfirm([...selected])}
        >
          Ingest selected ({selected.size})
        </button>
        <button
          type="button"
          className="rag-button"
          disabled={selectedIndexed === 0 || migrating || ingesting}
          onClick={onBulkClearIndex}
        >
          Clear index ({selectedIndexed})
        </button>
        <button
          type="button"
          className="rag-button"
          disabled={selected.size === 0 || migrating || ingesting}
          onClick={onBulkDelete}
        >
          Delete selected ({selected.size})
        </button>
        <input
          className="rag-input"
          placeholder="Filter filename or content"
          value={keyword}
          onChange={(e) => {
            setPage(1);
            setKeyword(e.target.value);
          }}
        />
      </div>

      {toast && <div className="rag-toast">{toast}</div>}
      {error && <div className="rag-error">{error}</div>}

      <IngestConfirmDialog
        open={ingestConfirmOpen}
        preview={ingestPreview}
        confirming={confirmingIngest}
        onConfirm={onConfirmIngest}
        onClose={() => {
          setIngestConfirmOpen(false);
          setPendingIngestIds([]);
        }}
      />
      <IngestProgressModal
        open={progressOpen}
        title="Ingest progress"
        relativePath={ingestRelativePath}
        workflowLog={ingestLog}
        activePhase={ingestActivePhase}
        loading={ingesting}
        onClose={() => !ingesting && setProgressOpen(false)}
      />

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
              onIngest={(id) => openIngestConfirm([id])}
              onClearIndex={onClearIndex}
              globalMigrating={migrating}
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
