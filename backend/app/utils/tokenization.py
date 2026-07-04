"""
utils/tokenization.py — Approximate token counting + text preview.

Per the JS-side utility (src/lib/rag/utils.ts), v1 uses a robust heuristic that
is accurate enough for observability metadata:
  • ~4 chars/token for Latin scripts
  • ~1.5 chars/token for CJK (Chinese/Japanese/Korean)

If the BGE-M3 tokenizer is loaded in-process (via services/embedding.py), the
embedder can override this with an exact count — see `approx_token_count_with_tokenizer`.
"""

from __future__ import annotations

import re
from typing import Optional

_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")


def approx_token_count(text: Optional[str]) -> int:
    """Heuristic token count (mirrors src/lib/rag/utils.ts approxTokenCount)."""
    if not text:
        return 0
    cjk = len(_CJK_RE.findall(text))
    other = len(text) - cjk
    # ceil to avoid zero-token non-empty strings
    return max(1, (cjk + 1) // 2 + (other + 3) // 4) if (cjk or other) else 0


def preview(text: Optional[str], max_len: int = 220) -> str:
    """Single-line preview truncated to `max_len` chars with ellipsis."""
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[:max_len] + "…"


def approx_token_count_with_tokenizer(text: str, tokenizer) -> int:
    """Exact token count using a HuggingFace tokenizer (best-effort)."""
    if not text:
        return 0
    try:
        ids = tokenizer.encode(text, add_special_tokens=False)
        return len(ids)
    except Exception:
        return approx_token_count(text)
