/** Session payload persisted from /rag/search for /rag/memory save flow. */

import type { SearchHit } from "./search";

export const MEMORY_SESSION_STORAGE_KEY = "rag:memory:search-session";

export interface MemorySearchSession {
  query: string;
  hits: SearchHit[];
  span_id?: string | null;
  session_id: string;
  saved_at: string;
}

export function saveMemorySearchSession(session: MemorySearchSession): void {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(MEMORY_SESSION_STORAGE_KEY, JSON.stringify(session));
}

export function loadMemorySearchSession(): MemorySearchSession | null {
  if (typeof window === "undefined") return null;
  const raw = sessionStorage.getItem(MEMORY_SESSION_STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as MemorySearchSession;
  } catch {
    return null;
  }
}

export function clearMemorySearchSession(): void {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(MEMORY_SESSION_STORAGE_KEY);
}
