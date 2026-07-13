/** RAG Content Vault API client — `/api/v1/rag/vault/*` */

export type VaultIndexStatus =
  | "not_indexed"
  | "pending"
  | "indexed"
  | "modified"
  | "error"
  | "deleted";

export interface VaultFolder {
  id: string;
  name: string;
  slug: string;
  created_at: string;
  relative_path: string;
  file_count: number;
}

export interface FolderRenamePreviewFile {
  old_relative_path: string;
  new_relative_path: string;
  index_status: VaultIndexStatus;
}

export interface FolderRenamePreview {
  folder_id: string;
  old_name: string;
  new_name: string;
  old_slug: string;
  new_slug: string;
  slug_unchanged: boolean;
  can_rename: boolean;
  block_reason?: string | null;
  total_files: number;
  neo4j_knowledge_count: number;
  preview_files: FolderRenamePreviewFile[];
  has_more_files: boolean;
}

export interface VaultFile {
  id: string;
  folder_id: string;
  filename: string;
  relative_path: string;
  source: string;
  created_at: string;
  updated_at: string;
  size_bytes: number;
  mime_ext: string;
  mutable: boolean;
  index_status: VaultIndexStatus;
  chunk_count: number;
  last_ingest_job_id?: string | null;
  last_ingest_at?: string | null;
  ingest_locked: boolean;
  error_message?: string | null;
  content_preview?: string | null;
}

export interface PaginatedFilesResponse {
  files: VaultFile[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface SyncReport {
  files_scanned: number;
  drift_added: number;
  drift_modified: number;
  drift_removed: number;
  last_sync_at?: string | null;
}

export interface UploadResponse {
  file: VaultFile;
  ingest_job_id?: string | null;
  replaced?: boolean;
}

export interface BatchUploadFileResult {
  file_id: string;
  filename: string;
  job_id?: string | null;
  status: string;
  error_message?: string | null;
}

export interface BatchUploadResponse {
  batch_id: string;
  files: BatchUploadFileResult[];
}

export interface BatchDeleteResult {
  results: { file_id: string; ok: boolean; error?: string | null }[];
}

const API_BASE = "/api/v1/rag/vault";

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || res.statusText);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

export async function listFolders(): Promise<VaultFolder[]> {
  const res = await fetch(`${API_BASE}/folders`);
  const data = await handleResponse<{ folders: VaultFolder[] }>(res);
  return data.folders;
}

export async function createFolder(name: string): Promise<VaultFolder> {
  const res = await fetch(`${API_BASE}/folders`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  return handleResponse<VaultFolder>(res);
}

export async function previewFolderRename(
  folderId: string,
  name: string
): Promise<FolderRenamePreview> {
  const qs = new URLSearchParams({ name });
  const res = await fetch(`${API_BASE}/folders/${folderId}/rename-preview?${qs}`);
  return handleResponse<FolderRenamePreview>(res);
}

export async function renameFolder(folderId: string, name: string): Promise<VaultFolder> {
  const res = await fetch(`${API_BASE}/folders/${folderId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  return handleResponse<VaultFolder>(res);
}

export async function deleteFolder(folderId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/folders/${folderId}`, { method: "DELETE" });
  await handleResponse<void>(res);
}

export async function listVaultFiles(params: {
  folder_id?: string;
  keyword?: string;
  index_status?: string;
  search_content?: boolean;
  page?: number;
  page_size?: number;
}): Promise<PaginatedFilesResponse> {
  const search = new URLSearchParams();
  if (params.folder_id) search.set("folder_id", params.folder_id);
  if (params.keyword) search.set("keyword", params.keyword);
  if (params.index_status) search.set("index_status", params.index_status);
  if (params.search_content) search.set("search_content", "true");
  if (params.page) search.set("page", String(params.page));
  if (params.page_size) search.set("page_size", String(params.page_size));
  const qs = search.toString();
  const res = await fetch(`${API_BASE}/files${qs ? `?${qs}` : ""}`);
  return handleResponse<PaginatedFilesResponse>(res);
}

export async function createVaultFile(body: {
  folder_id: string;
  filename: string;
  content?: string;
}): Promise<UploadResponse> {
  const res = await fetch(`${API_BASE}/files`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handleResponse<UploadResponse>(res);
}

export async function uploadVaultFile(
  folderId: string,
  file: File
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("folder_id", folderId);
  form.append("file", file);
  const res = await fetch(`${API_BASE}/files/upload`, { method: "POST", body: form });
  return handleResponse<UploadResponse>(res);
}

export async function batchUploadVaultFiles(
  folderId: string,
  files: File[]
): Promise<BatchUploadResponse> {
  const form = new FormData();
  form.append("folder_id", folderId);
  for (const f of files) {
    form.append("files", f);
  }
  const res = await fetch(`${API_BASE}/files/batch-upload`, { method: "POST", body: form });
  return handleResponse<BatchUploadResponse>(res);
}

export async function getVaultFileContent(fileId: string): Promise<{
  id: string;
  relative_path: string;
  content: string;
  size: number;
}> {
  const res = await fetch(`${API_BASE}/files/${fileId}/content`);
  return handleResponse(res);
}

export async function getVaultFileByPath(relativePath: string): Promise<VaultFile | null> {
  const listed = await listVaultFiles({ keyword: relativePath.split("/").pop(), page_size: 20 });
  return listed.files.find((f) => f.relative_path === relativePath) ?? null;
}

export async function saveVaultFileContent(
  fileId: string,
  content: string
): Promise<UploadResponse> {
  const res = await fetch(`${API_BASE}/files/${fileId}/content`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  return handleResponse<UploadResponse>(res);
}

export async function batchDeleteVaultFiles(fileIds: string[]): Promise<BatchDeleteResult> {
  const res = await fetch(`${API_BASE}/files/batch`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file_ids: fileIds }),
  });
  return handleResponse<BatchDeleteResult>(res);
}

export async function reindexVaultFile(fileId: string): Promise<{
  file_id: string;
  relative_path: string;
  ingest_job_id: string;
}> {
  const res = await fetch(`${API_BASE}/files/${fileId}/reindex`, { method: "POST" });
  return handleResponse(res);
}

export interface IngestPreviewItem {
  file_id: string;
  relative_path: string;
  estimated_tokens: number;
  ingestible: boolean;
  block_reason?: string | null;
}

export interface IngestPreviewResponse {
  items: IngestPreviewItem[];
  total_estimated_tokens: number;
  file_count: number;
}

export async function previewIngest(fileIds: string[]): Promise<IngestPreviewResponse> {
  const res = await fetch(`${API_BASE}/files/ingest-preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file_ids: fileIds }),
  });
  return handleResponse(res);
}

export async function ingestVaultFile(fileId: string): Promise<{
  file_id: string;
  relative_path: string;
  ingest_job_id: string;
}> {
  const res = await fetch(`${API_BASE}/files/${fileId}/ingest`, { method: "POST" });
  return handleResponse(res);
}

export interface BatchIngestSkippedItem {
  file_id: string;
  reason: string;
}

export interface BatchIngestResponse {
  batch_id: string;
  queued: string[];
  skipped: BatchIngestSkippedItem[];
}

export async function batchIngestVaultFiles(fileIds: string[]): Promise<BatchIngestResponse> {
  const res = await fetch(`${API_BASE}/files/batch-ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file_ids: fileIds }),
  });
  return handleResponse(res);
}

export async function clearVaultIndex(fileId: string): Promise<{
  file_id: string;
  relative_path: string;
  index_status: VaultIndexStatus;
}> {
  const res = await fetch(`${API_BASE}/files/${fileId}/clear-index`, { method: "POST" });
  return handleResponse(res);
}

export interface MigrateV16JobEntry {
  file_id: string;
  relative_path: string;
  ingest_job_id: string;
}

export interface MigrateV16Response {
  total_files: number;
  job_ids: MigrateV16JobEntry[];
  dry_run?: boolean;
  neo4j_stats?: Record<string, number>;
  redis_keys_deleted?: number;
}

export async function migrateVaultV16(params?: {
  purge_mode?: "vault" | "all";
  dry_run?: boolean;
}): Promise<MigrateV16Response> {
  const search = new URLSearchParams();
  if (params?.purge_mode) search.set("purge_mode", params.purge_mode);
  if (params?.dry_run) search.set("dry_run", "true");
  const qs = search.toString();
  const res = await fetch(`${API_BASE}/migrate-v16${qs ? `?${qs}` : ""}`, { method: "POST" });
  return handleResponse<MigrateV16Response>(res);
}

export async function syncVault(): Promise<SyncReport> {
  const res = await fetch(`${API_BASE}/sync`, { method: "POST" });
  return handleResponse<SyncReport>(res);
}

export async function getBatchStatus(batchId: string) {
  const res = await fetch(`${API_BASE}/batches/${batchId}`);
  return handleResponse<{
    id: string;
    total_files: number;
    completed_files: number;
    failed_files: number;
    files: BatchUploadFileResult[];
  }>(res);
}

export function languageFromPath(path: string): string {
  if (path.endsWith(".md")) return "markdown";
  if (path.endsWith(".py")) return "python";
  if (path.endsWith(".sql")) return "sql";
  return "plaintext";
}
