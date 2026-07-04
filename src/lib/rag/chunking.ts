/**
 * ChunkingModule — PURE boundary detection. STRICT MODULE BOUNDARY:
 *   - This module ONLY finds boundaries. It never embeds, never persists, never
 *     coordinates. Called by the PipelineOrchestrator.
 *   (Mirrors services/chunking.py from backend-directory-structure spec.)
 *
 * Supported methods (v1 — standard paths only, NO Late/Agentic):
 *   • LongText          — sliding window (~8k tokens, 10% overlap). For the
 *                         LongText embedding approach (whole-doc or windows).
 *   • Recursive         — recursive character splitter (markdown-aware) with
 *                         overlap, target ~512 tokens.
 *   • Semantic          — sentence-clustering by adjacent cosine similarity
 *                         (simple, deterministic — no LLM calls in v1).
 *   • Structure-Aware   — splits on markdown headings; records section path.
 */

import {
  CHUNK_OVERLAP_TOKENS,
  CHUNK_TARGET_TOKENS,
  LONGTEXT_OVERLAP_TOKENS,
  LONGTEXT_WINDOW_TOKENS,
} from "./constants";
import type { ChunkMethod } from "./types";
import { approxTokenCount } from "./utils";

export interface ChunkBoundary {
  index: number;
  text: string;
  charStart: number;
  charEnd: number;
  section?: string; // Structure-Aware: heading path (e.g. "# Intro > ## Background")
  tokenCount: number;
}

// ─── LongText (sliding window) ──────────────────────────────────────────────

export function chunkLongText(text: string): ChunkBoundary[] {
  const target = LONGTEXT_WINDOW_TOKENS;
  const overlap = LONGTEXT_OVERLAP_TOKENS;
  if (!text || text.trim().length === 0) return [];

  // If the whole doc fits comfortably, emit a single window (true LongText).
  const totalTokens = approxTokenCount(text);
  if (totalTokens <= target) {
    return [
      {
        index: 0,
        text,
        charStart: 0,
        charEnd: text.length,
        tokenCount: totalTokens,
      },
    ];
  }

  // Otherwise sliding window by characters (approx tokens → chars at ~4 chars/token).
  const charWindow = target * 4;
  const charOverlap = overlap * 4;
  const boundaries: ChunkBoundary[] = [];
  let pos = 0;
  let idx = 0;
  while (pos < text.length) {
    let end = Math.min(pos + charWindow, text.length);
    // Try to break at a paragraph/sentence boundary within the last 15% of window.
    const searchStart = pos + Math.floor(charWindow * 0.85);
    const breakPoint = findBreakPoint(text, searchStart, end);
    if (breakPoint > pos) end = breakPoint;
    const chunkText = text.slice(pos, end);
    boundaries.push({
      index: idx++,
      text: chunkText,
      charStart: pos,
      charEnd: end,
      tokenCount: approxTokenCount(chunkText),
    });
    if (end >= text.length) break;
    pos = Math.max(pos + 1, end - charOverlap);
  }
  return boundaries;
}

// ─── Recursive (markdown-aware character splitter) ──────────────────────────

export function chunkRecursive(text: string): ChunkBoundary[] {
  return recursiveSplit(text, 0, text.length, 0);
}

function recursiveSplit(
  text: string,
  start: number,
  end: number,
  depth: number,
): ChunkBoundary[] {
  const chunk = text.slice(start, end);
  const tokens = approxTokenCount(chunk);
  const target = CHUNK_TARGET_TOKENS.Recursive;
  if (tokens <= target * 1.2 || depth > 6) {
    return [{ index: 0, text: chunk, charStart: start, charEnd: end, tokenCount: tokens }];
  }
  // Try splitters in priority order (markdown-aware).
  const splitters = [
    /\n#{1,6}\s+/g, // headings
    /\n```\n/g, // code blocks
    /\n\n+/g, // paragraphs
    /\n(?=\s*[-*]\s)/g, // list items
    /\n/g, // lines
    /(?<=[.!?。！？])\s+/g, // sentences
  ];
  const splitter = splitters[depth] ?? splitters[splitters.length - 1];
  const segments = splitOn(chunk, splitter, start);
  if (segments.length <= 1) {
    // Can't split further with this splitter; force-split by target size.
    return forceSplit(chunk, start, target, CHUNK_OVERLAP_TOKENS);
  }
  // Greedily merge segments up to target size.
  const result: ChunkBoundary[] = [];
  let buf = { text: "", start: segments[0].start, end: segments[0].start };
  let idx = 0;
  for (const seg of segments) {
    if (approxTokenCount(buf.text + seg.text) > target && buf.text.length > 0) {
      result.push({
        index: idx++,
        text: buf.text,
        charStart: buf.start,
        charEnd: buf.end,
        tokenCount: approxTokenCount(buf.text),
      });
      // Overlap: carry last ~overlap tokens of buffer into next.
      const overlapText = tailTokens(buf.text, CHUNK_OVERLAP_TOKENS);
      buf = { text: overlapText + seg.text, start: buf.end - overlapText.length, end: seg.end };
    } else {
      buf.text += seg.text;
      buf.end = seg.end;
    }
  }
  if (buf.text.length > 0) {
    result.push({
      index: idx++,
      text: buf.text,
      charStart: buf.start,
      charEnd: buf.end,
      tokenCount: approxTokenCount(buf.text),
    });
  }
  // If still too few chunks (greedy didn't split enough), recurse on oversized.
  const final: ChunkBoundary[] = [];
  let gi = 0;
  for (const c of result) {
    if (approxTokenCount(c.text) > target * 1.8) {
      const sub = recursiveSplit(c.text, c.charStart, c.charEnd, depth + 1).map((s, i) => ({
        ...s,
        index: gi + i,
      }));
      gi += sub.length;
      final.push(...sub);
    } else {
      final.push({ ...c, index: gi++ });
    }
  }
  return final;
}

function splitOn(text: string, regex: RegExp, baseOffset: number): { text: string; start: number; end: number }[] {
  const segments: { text: string; start: number; end: number }[] = [];
  let lastEnd = 0;
  let m: RegExpExecArray | null;
  const re = new RegExp(regex.source, regex.flags.includes("g") ? regex.flags : regex.flags + "g");
  while ((m = re.exec(text)) !== null) {
    if (m.index > lastEnd) {
      segments.push({ text: text.slice(lastEnd, m.index), start: baseOffset + lastEnd, end: baseOffset + m.index });
    }
    lastEnd = m.index + m[0].length;
    if (m.index === re.lastIndex) re.lastIndex++;
  }
  if (lastEnd < text.length) {
    segments.push({ text: text.slice(lastEnd), start: baseOffset + lastEnd, end: baseOffset + text.length });
  }
  return segments.filter((s) => s.text.trim().length > 0);
}

function forceSplit(text: string, base: number, targetTokens: number, overlapTokens: number): ChunkBoundary[] {
  const charTarget = targetTokens * 4;
  const charOverlap = overlapTokens * 4;
  const result: ChunkBoundary[] = [];
  let pos = 0;
  let idx = 0;
  while (pos < text.length) {
    let end = Math.min(pos + charTarget, text.length);
    const bp = findBreakPoint(text, pos + charTarget * 0.85, end);
    if (bp > pos) end = bp;
    result.push({
      index: idx++,
      text: text.slice(pos, end),
      charStart: base + pos,
      charEnd: base + end,
      tokenCount: approxTokenCount(text.slice(pos, end)),
    });
    if (end >= text.length) break;
    pos = Math.max(pos + 1, end - charOverlap);
  }
  return result;
}

function tailTokens(text: string, tokens: number): string {
  const charLen = tokens * 4;
  return text.length > charLen ? text.slice(text.length - charLen) : text;
}

// ─── Semantic (adjacent sentence similarity clustering) ─────────────────────

export function chunkSemantic(text: string): ChunkBoundary[] {
  const sentences = splitSentences(text);
  if (sentences.length === 0) return [];
  const target = CHUNK_TARGET_TOKENS.Semantic;
  // Compute a simple "semantic" signal via token-overlap between adjacent sentences.
  const boundaries: ChunkBoundary[] = [];
  let buf = sentences[0].text;
  let bufStart = sentences[0].start;
  let bufEnd = sentences[0].end;
  let idx = 0;
  for (let i = 1; i < sentences.length; i++) {
    const s = sentences[i];
    const sim = jaccard(tokensForSim(buf), tokensForSim(s.text));
    const combinedTokens = approxTokenCount(buf + s.text);
    // If similar enough AND not too big, merge. Else flush.
    if (sim > 0.15 && combinedTokens < target * 1.5) {
      buf += s.text;
      bufEnd = s.end;
    } else {
      if (buf.trim().length > 0) {
        boundaries.push({
          index: idx++,
          text: buf,
          charStart: bufStart,
          charEnd: bufEnd,
          tokenCount: approxTokenCount(buf),
        });
      }
      // Overlap: start new buffer with tail of previous.
      const tail = tailTokens(buf, CHUNK_OVERLAP_TOKENS);
      buf = tail + s.text;
      bufStart = bufEnd - tail.length;
      bufEnd = s.end;
    }
  }
  if (buf.trim().length > 0) {
    boundaries.push({
      index: idx++,
      text: buf,
      charStart: bufStart,
      charEnd: bufEnd,
      tokenCount: approxTokenCount(buf),
    });
  }
  return boundaries;
}

function splitSentences(text: string): { text: string; start: number; end: number }[] {
  const result: { text: string; start: number; end: number }[] = [];
  const re = /[^.!?。！？\n]+[.!?。！？]*/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    const s = m[0];
    if (s.trim().length > 0) {
      result.push({ text: s, start: m.index, end: m.index + s.length });
    }
  }
  return result;
}

function tokensForSim(text: string): Set<string> {
  return new Set(
    text.toLowerCase().split(/[^a-z0-9\u4e00-\u9fff]+/i).filter((t) => t.length > 2),
  );
}

function jaccard(a: Set<string>, b: Set<string>): number {
  if (a.size === 0 || b.size === 0) return 0;
  let inter = 0;
  for (const t of a) if (b.has(t)) inter++;
  return inter / (a.size + b.size - inter);
}

// ─── Structure-Aware (markdown heading path) ────────────────────────────────

export function chunkStructureAware(text: string): ChunkBoundary[] {
  const target = CHUNK_TARGET_TOKENS["Structure-Aware"];
  const lines = text.split("\n");
  const sections: { path: string; text: string; start: number }[] = [];
  const headingStack: { level: number; text: string }[] = [];
  let currentText = "";
  let currentStart = 0;
  let currentPath = "";

  // Walk lines tracking char offset.
  let offset = 0;
  const flush = () => {
    if (currentText.trim().length > 0) {
      sections.push({ path: currentPath, text: currentText, start: currentStart });
    }
    currentText = "";
  };
  for (const line of lines) {
    const lineStart = offset;
    const headingMatch = line.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      flush();
      const level = headingMatch[1].length;
      const title = headingMatch[2].trim();
      while (headingStack.length && headingStack[headingStack.length - 1].level >= level) {
        headingStack.pop();
      }
      headingStack.push({ level, text: title });
      currentPath = headingStack.map((h) => h.text).join(" > ") || "Root";
      currentStart = lineStart;
      currentText = line + "\n";
    } else {
      if (currentText.length === 0) currentStart = lineStart;
      currentText += line + "\n";
    }
    offset += line.length + 1; // +1 for \n
  }
  flush();

  // Sub-chunk each section by target size (recursive within section).
  const boundaries: ChunkBoundary[] = [];
  let idx = 0;
  for (const sec of sections) {
    if (approxTokenCount(sec.text) <= target * 1.3) {
      boundaries.push({
        index: idx++,
        text: sec.text,
        charStart: sec.start,
        charEnd: sec.start + sec.text.length,
        section: sec.path || undefined,
        tokenCount: approxTokenCount(sec.text),
      });
    } else {
      const sub = forceSplit(sec.text, sec.start, target, CHUNK_OVERLAP_TOKENS);
      for (const s of sub) {
        boundaries.push({ ...s, index: idx++, section: sec.path || undefined });
      }
    }
  }
  return boundaries;
}

// ─── Public dispatcher ──────────────────────────────────────────────────────

export function determineBoundaries(text: string, method: ChunkMethod): ChunkBoundary[] {
  switch (method) {
    case "Recursive":
      return chunkRecursive(text);
    case "Semantic":
      return chunkSemantic(text);
    case "Structure-Aware":
      return chunkStructureAware(text);
    default:
      throw new Error(`Unsupported chunk method: ${method}`);
  }
}

// ─── Shared helpers ─────────────────────────────────────────────────────────

function findBreakPoint(text: string, searchStart: number, searchEnd: number): number {
  // Prefer paragraph break, then sentence, then space.
  const region = text.slice(searchStart, searchEnd);
  const para = region.lastIndexOf("\n\n");
  if (para !== -1) return searchStart + para + 2;
  const sentence = region.search(/(?<=[.!?。！？])\s/);
  if (sentence !== -1) return searchStart + sentence + 1;
  const space = region.lastIndexOf(" ");
  if (space !== -1) return searchStart + space + 1;
  return searchEnd;
}
