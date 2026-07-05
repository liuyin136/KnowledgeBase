"""
services/chunking.py — ChunkingModule.

STRICT MODULE BOUNDARY (Backend §2):
  • This module ONLY finds chunk boundaries. It NEVER embeds, NEVER persists,
    NEVER coordinates. Called exclusively by the PipelineOrchestrator.
  • Mirrors src/lib/rag/chunking.ts (the JS reference implementation) so the
    FastAPI backend produces equivalent boundaries for the same input.

Supported methods (v1 — standard paths only, NO Late/Agentic):
  • LongText          — sliding window (default 30000 tokens via config, 10% overlap). For the
                        LongText embedding approach. Pure boundary detection —
                        the windows ARE the retrieval units (stored as :Knowledge).
  • Recursive         — recursive character splitter (markdown-aware) with
                        overlap, target ~512 tokens.
  • Semantic          — sentence-clustering by adjacent token-overlap similarity
                        (simple, deterministic — no LLM calls in v1).
  • Structure-Aware   — splits on markdown headings; records section path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from app.core.config import settings
from app.core.constants import (
    CHUNK_OVERLAP_TOKENS,
    CHUNK_TARGET_TOKENS,
)
from app.utils.tokenization import approx_token_count


@dataclass
class ChunkBoundary:
    """A pure chunk boundary — no embedding, no persistence metadata."""

    index: int
    text: str
    char_start: int
    char_end: int
    token_count: int
    section: Optional[str] = None  # Structure-Aware: heading path


# ─── LongText (sliding window) ────────────────────────────────────────────────


def chunk_long_text(text: str) -> List[ChunkBoundary]:
    # Use runtime config (user can override via env / settings.longtext_window_tokens)
    # Default now 30000 (updated for larger context windows).
    target = settings.longtext_window_tokens
    overlap = settings.longtext_overlap_tokens
    if not text or not text.strip():
        return []

    total_tokens = approx_token_count(text)
    # If the whole doc fits comfortably, emit a single window (true LongText).
    if total_tokens <= target:
        return [
            ChunkBoundary(
                index=0,
                text=text,
                char_start=0,
                char_end=len(text),
                token_count=total_tokens,
            )
        ]

    char_window = target * 4
    char_overlap = overlap * 4
    boundaries: List[ChunkBoundary] = []
    pos = 0
    idx = 0
    while pos < len(text):
        end = min(pos + char_window, len(text))
        # Try to break at a paragraph/sentence boundary within the last 15% of window.
        search_start = pos + int(char_window * 0.85)
        bp = _find_break_point(text, search_start, end)
        if bp > pos:
            end = bp
        chunk_text = text[pos:end]
        boundaries.append(
            ChunkBoundary(
                index=idx,
                text=chunk_text,
                char_start=pos,
                char_end=end,
                token_count=approx_token_count(chunk_text),
            )
        )
        idx += 1
        if end >= len(text):
            break
        pos = max(pos + 1, end - char_overlap)
    return boundaries


# ─── Recursive (markdown-aware character splitter) ────────────────────────────


def chunk_recursive(text: str) -> List[ChunkBoundary]:
    return _recursive_split(text, 0, len(text), 0)


def _recursive_split(text: str, start: int, end: int, depth: int) -> List[ChunkBoundary]:
    chunk = text[start:end]
    tokens = approx_token_count(chunk)
    target = CHUNK_TARGET_TOKENS["Recursive"]
    if tokens <= target * 1.2 or depth > 6:
        return [ChunkBoundary(index=0, text=chunk, char_start=start, char_end=end, token_count=tokens)]

    splitters = [
        re.compile(r"\n#{1,6}\s+"),
        re.compile(r"\n```\n"),
        re.compile(r"\n\n+"),
        re.compile(r"\n(?=\s*[-*]\s)"),
        re.compile(r"\n"),
        re.compile(r"(?<=[.!?。！？])\s+"),
    ]
    splitter = splitters[depth] if depth < len(splitters) else splitters[-1]
    segments = _split_on(chunk, splitter, start)
    if len(segments) <= 1:
        # Can't split further with this splitter; force-split by target size.
        return _force_split(chunk, start, target, CHUNK_OVERLAP_TOKENS)

    # Greedily merge segments up to target size.
    result: List[ChunkBoundary] = []
    buf_text = ""
    buf_start = segments[0].start
    buf_end = segments[0].start
    idx = 0
    for seg in segments:
        if approx_token_count(buf_text + seg.text) > target and buf_text:
            result.append(
                ChunkBoundary(
                    index=idx,
                    text=buf_text,
                    char_start=buf_start,
                    char_end=buf_end,
                    token_count=approx_token_count(buf_text),
                )
            )
            idx += 1
            # Overlap: carry last ~overlap tokens of buffer into next.
            overlap_text = _tail_tokens(buf_text, CHUNK_OVERLAP_TOKENS)
            buf_text = overlap_text + seg.text
            buf_start = buf_end - len(overlap_text)
            buf_end = seg.end
        else:
            buf_text += seg.text
            buf_end = seg.end
    if buf_text:
        result.append(
            ChunkBoundary(
                index=idx,
                text=buf_text,
                char_start=buf_start,
                char_end=buf_end,
                token_count=approx_token_count(buf_text),
            )
        )

    # If still too few chunks (greedy didn't split enough), recurse on oversized.
    final: List[ChunkBoundary] = []
    gi = 0
    for c in result:
        if approx_token_count(c.text) > target * 1.8:
            sub = _recursive_split(c.text, c.char_start, c.char_end, depth + 1)
            for s in sub:
                final.append(ChunkBoundary(index=gi, text=s.text, char_start=s.char_start, char_end=s.char_end,
                                           token_count=s.token_count, section=s.section))
                gi += 1
        else:
            final.append(ChunkBoundary(index=gi, text=c.text, char_start=c.char_start, char_end=c.char_end,
                                       token_count=c.token_count))
            gi += 1
    return final


@dataclass
class _Segment:
    text: str
    start: int
    end: int


def _split_on(text: str, regex: re.Pattern, base_offset: int) -> List[_Segment]:
    segments: List[_Segment] = []
    last_end = 0
    for m in regex.finditer(text):
        if m.start() > last_end:
            segments.append(_Segment(text=text[last_end : m.start()], start=base_offset + last_end,
                                     end=base_offset + m.start()))
        last_end = m.end()
    if last_end < len(text):
        segments.append(_Segment(text=text[last_end:], start=base_offset + last_end,
                                 end=base_offset + len(text)))
    return [s for s in segments if s.text.strip()]


def _force_split(text: str, base: int, target_tokens: int, overlap_tokens: int) -> List[ChunkBoundary]:
    char_target = target_tokens * 4
    char_overlap = overlap_tokens * 4
    result: List[ChunkBoundary] = []
    pos = 0
    idx = 0
    while pos < len(text):
        end = min(pos + char_target, len(text))
        bp = _find_break_point(text, pos + int(char_target * 0.85), end)
        if bp > pos:
            end = bp
        result.append(
            ChunkBoundary(
                index=idx,
                text=text[pos:end],
                char_start=base + pos,
                char_end=base + end,
                token_count=approx_token_count(text[pos:end]),
            )
        )
        idx += 1
        if end >= len(text):
            break
        pos = max(pos + 1, end - char_overlap)
    return result


def _tail_tokens(text: str, tokens: int) -> str:
    char_len = tokens * 4
    return text[-char_len:] if len(text) > char_len else text


# ─── Semantic (adjacent sentence similarity clustering) ───────────────────────


def chunk_semantic(text: str) -> List[ChunkBoundary]:
    sentences = _split_sentences(text)
    if not sentences:
        return []
    target = CHUNK_TARGET_TOKENS["Semantic"]
    boundaries: List[ChunkBoundary] = []
    buf = sentences[0].text
    buf_start = sentences[0].start
    buf_end = sentences[0].end
    idx = 0
    for s in sentences[1:]:
        sim = _jaccard(_tokens_for_sim(buf), _tokens_for_sim(s.text))
        combined_tokens = approx_token_count(buf + s.text)
        # If similar enough AND not too big, merge. Else flush.
        if sim > 0.15 and combined_tokens < target * 1.5:
            buf += s.text
            buf_end = s.end
        else:
            if buf.strip():
                boundaries.append(
                    ChunkBoundary(
                        index=idx,
                        text=buf,
                        char_start=buf_start,
                        char_end=buf_end,
                        token_count=approx_token_count(buf),
                    )
                )
                idx += 1
            # Overlap: start new buffer with tail of previous.
            tail = _tail_tokens(buf, CHUNK_OVERLAP_TOKENS)
            buf = tail + s.text
            buf_start = buf_end - len(tail)
            buf_end = s.end
    if buf.strip():
        boundaries.append(
            ChunkBoundary(
                index=idx,
                text=buf,
                char_start=buf_start,
                char_end=buf_end,
                token_count=approx_token_count(buf),
            )
        )
    return boundaries


def _split_sentences(text: str) -> List[_Segment]:
    result: List[_Segment] = []
    for m in re.finditer(r"[^.!?。！？\n]+[.!?。！？]*", text):
        s = m.group(0)
        if s.strip():
            result.append(_Segment(text=s, start=m.start(), end=m.end()))
    return result


def _tokens_for_sim(text: str) -> set:
    return {t for t in re.split(r"[^a-z0-9\u4e00-\u9fff]+", text.lower()) if len(t) > 2}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


# ─── Structure-Aware (markdown heading path) ──────────────────────────────────


def chunk_structure_aware(text: str) -> List[ChunkBoundary]:
    target = CHUNK_TARGET_TOKENS["Structure-Aware"]
    lines = text.split("\n")
    sections: List[_Section] = []
    heading_stack: List[_Heading] = []
    current_text = ""
    current_start = 0
    current_path = ""

    offset = 0

    def flush() -> None:
        nonlocal current_text
        if current_text.strip():
            sections.append(_Section(path=current_path, text=current_text, start=current_start))
        current_text = ""

    for line in lines:
        line_start = offset
        m = re.match(r"^(#{1,6})\s+(.+)$", line)
        if m:
            flush()
            level = len(m.group(1))
            title = m.group(2).strip()
            while heading_stack and heading_stack[-1].level >= level:
                heading_stack.pop()
            heading_stack.append(_Heading(level=level, text=title))
            current_path = " > ".join(h.text for h in heading_stack) or "Root"
            current_start = line_start
            current_text = line + "\n"
        else:
            if not current_text:
                current_start = line_start
            current_text += line + "\n"
        offset += len(line) + 1  # +1 for \n
    flush()

    boundaries: List[ChunkBoundary] = []
    idx = 0
    for sec in sections:
        if approx_token_count(sec.text) <= target * 1.3:
            boundaries.append(
                ChunkBoundary(
                    index=idx,
                    text=sec.text,
                    char_start=sec.start,
                    char_end=sec.start + len(sec.text),
                    token_count=approx_token_count(sec.text),
                    section=sec.path or None,
                )
            )
            idx += 1
        else:
            sub = _force_split(sec.text, sec.start, target, CHUNK_OVERLAP_TOKENS)
            for s in sub:
                boundaries.append(
                    ChunkBoundary(
                        index=idx,
                        text=s.text,
                        char_start=s.char_start,
                        char_end=s.char_end,
                        token_count=s.token_count,
                        section=sec.path or None,
                    )
                )
                idx += 1
    return boundaries


@dataclass
class _Heading:
    level: int
    text: str


@dataclass
class _Section:
    path: str
    text: str
    start: int


# ─── Public dispatcher ────────────────────────────────────────────────────────


def determine_boundaries(text: str, method: str) -> List[ChunkBoundary]:
    """Dispatch to the appropriate chunker. `method` is a ChunkMethod value
    (Recursive / Semantic / Structure-Aware) — LongText is handled separately
    via `chunk_long_text` because it doesn't take a method argument."""
    if method == "Recursive":
        return chunk_recursive(text)
    if method == "Semantic":
        return chunk_semantic(text)
    if method == "Structure-Aware":
        return chunk_structure_aware(text)
    raise ValueError(f"Unsupported chunk method: {method}")


# ─── Shared helpers ───────────────────────────────────────────────────────────


def _find_break_point(text: str, search_start: int, search_end: int) -> int:
    """Prefer paragraph break, then sentence, then space."""
    if search_start >= len(text):
        return search_end
    region = text[search_start:search_end]
    para = region.rfind("\n\n")
    if para != -1:
        return search_start + para + 2
    m = re.search(r"(?<=[.!?。！？])\s", region)
    if m:
        return search_start + m.end()
    space = region.rfind(" ")
    if space != -1:
        return search_start + space + 1
    return search_end
