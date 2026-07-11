from __future__ import annotations

import hashlib
import re
from typing import Callable, TypeVar

from app.core.constants import CHUNK_TOKEN_MAX, OVERLAP_TOKENS, STRIDE_TOKENS
from app.models.neo4j_models import ChunkRecord

T = TypeVar("T")


def clean_text(raw: str) -> str:
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _default_tokenize(text: str) -> list[str]:
    return re.findall(r"\S+", text)


def _default_detokenize(tokens: list[str]) -> str:
    return " ".join(tokens)


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def chunk_document(
    raw: str,
    *,
    tokenize: Callable[[str], list[T]] | None = None,
    detokenize: Callable[[list[T]], str] | None = None,
    chunk_token_max: int = CHUNK_TOKEN_MAX,
    overlap_tokens: int = OVERLAP_TOKENS,
    stride_tokens: int = STRIDE_TOKENS,
) -> list[ChunkRecord]:
    tokenize = tokenize or _default_tokenize
    detokenize = detokenize or _default_detokenize

    cleaned = clean_text(raw)
    if not cleaned:
        return []

    tokens = tokenize(cleaned)
    total = len(tokens)

    if total <= chunk_token_max:
        windows = [tokens]
    else:
        windows = []
        k = 0
        while k * stride_tokens < total:
            start = k * stride_tokens
            end = min(start + chunk_token_max, total)
            windows.append(tokens[start:end])
            k += 1

    if len(windows) >= 2 and len(windows[-1]) < overlap_tokens:
        last = windows[-1]
        prev = windows[-2]
        k_last = len(windows) - 1
        start_prev = (k_last - 1) * stride_tokens
        end_prev = start_prev + len(prev)
        start_last = k_last * stride_tokens
        end_last = start_last + len(last)
        overlap_start_global = max(start_prev, end_prev - overlap_tokens)
        if start_last >= overlap_start_global and end_last <= end_prev:
            windows = windows[:-1]

    records: list[ChunkRecord] = []
    for i, window in enumerate(windows):
        start_token = 0 if i == 0 and total <= chunk_token_max else i * stride_tokens
        content = detokenize(window)
        records.append(
            ChunkRecord(
                chunk_index=i,
                content=content,
                content_hash=content_hash(content),
                token_count=len(window),
                start_token=start_token,
                end_token=start_token + len(window),
            )
        )
    return records
