export type Category = "RND" | "Daily" | "case";

export interface FileListItem {
  path: string;
  name: string;
  category: Category;
  modified_at: number;
}

export interface FileListResponse {
  files: FileListItem[];
  total: number;
}

export interface FileContentResponse {
  path: string;
  content: string;
  size: number;
}

export interface CreateLogRequest {
  category: Category;
  title: string;
  environment?: string;
  execution_step?: string;
  results?: string;
  next_steps?: string;
  symptom?: string;
  error_log?: string;
  investigation?: string;
  solution?: string;
  note?: string;
  done?: string;
  todo?: string;
  blocker?: string;
}

export interface CreateLogResponse {
  path: string;
  content: string;
}

const API_BASE = "/api/v1/files";

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || res.statusText);
  }
  return res.json() as Promise<T>;
}

export async function listFiles(params: {
  category?: Category;
  keyword?: string;
  date?: string;
}): Promise<FileListResponse> {
  const search = new URLSearchParams();
  if (params.category) search.set("category", params.category);
  if (params.keyword) search.set("keyword", params.keyword);
  if (params.date) search.set("date", params.date);
  const qs = search.toString();
  const res = await fetch(`${API_BASE}${qs ? `?${qs}` : ""}`);
  return handleResponse<FileListResponse>(res);
}

export async function getFileContent(path: string): Promise<FileContentResponse> {
  const res = await fetch(`${API_BASE}/content?path=${encodeURIComponent(path)}`);
  return handleResponse<FileContentResponse>(res);
}

export async function saveFileContent(
  path: string,
  content: string
): Promise<FileContentResponse> {
  const res = await fetch(`${API_BASE}/content`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, content }),
  });
  return handleResponse<FileContentResponse>(res);
}

export async function createLog(body: CreateLogRequest): Promise<CreateLogResponse> {
  const res = await fetch(API_BASE, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handleResponse<CreateLogResponse>(res);
}

export const CATEGORY_LABELS: Record<Category, string> = {
  RND: "R&D Log",
  Daily: "Daily Dev Log",
  case: "Troubleshooting Log",
};

export function languageFromPath(path: string): string {
  const ext = path.split(".").pop()?.toLowerCase();
  switch (ext) {
    case "md":
      return "markdown";
    case "py":
      return "python";
    case "sql":
      return "sql";
    default:
      return "plaintext";
  }
}
