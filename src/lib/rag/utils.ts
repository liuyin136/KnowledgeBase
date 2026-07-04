/**
 * Timing + tokenization utilities.
 * Mirrors utils/timing.py + utils/tokenization.py from backend-directory-structure spec.
 */

/** High-resolution monotonic millisecond timer. */
export function nowMs(): number {
  return performance.now();
}

/** Wrap an async fn and return [result, durationMs]. */
export async function timed<T>(fn: () => Promise<T>): Promise<[T, number]> {
  const start = nowMs();
  const result = await fn();
  return [result, nowMs() - start];
}

/** Wrap a sync fn and return [result, durationMs]. */
export function timedSync<T>(fn: () => T): [T, number] {
  const start = nowMs();
  const result = fn();
  return [result, nowMs() - start];
}

/**
 * Approximate token count. The directive assumes a BGE-M3 tokenizer; in this JS
 * stack we use a robust heuristic (~4 chars/token for English, ~1.5 chars/token
 * for CJK) which is accurate enough for v1 observability metadata. Real token
 * counts would require a WASM tokenizer — deferred post-v1.
 */
export function approxTokenCount(text: string): number {
  if (!text) return 0;
  // Count CJK characters
  const cjk = (text.match(/[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]/g) || []).length;
  const other = text.length - cjk;
  return Math.ceil(cjk / 1.5 + other / 4);
}

/** Truncate text to N chars with ellipsis for previews. */
export function preview(text: string, max = 200): string {
  if (!text) return "";
  const clean = text.replace(/\s+/g, " ").trim();
  return clean.length > max ? clean.slice(0, max) + "…" : clean;
}

/** Sleep helper (for retry backoff). */
export function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
