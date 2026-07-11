"""Lazy imports for Jina GGUF scripts (mounted under /app/scripts in worker)."""
from __future__ import annotations

import gc
import sys
from pathlib import Path
from typing import Any, Callable

import numpy as np

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
_JINA_DIR = _SCRIPTS / "Jina"
if str(_JINA_DIR) not in sys.path:
    sys.path.insert(0, str(_JINA_DIR))
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

_active_slot: str | None = None


def _acquire_slot(name: str) -> None:
    global _active_slot
    if _active_slot is not None:
        raise RuntimeError(f"GPU model slot busy: {_active_slot} (requested {name})")
    _active_slot = name


def _release_slot(name: str) -> None:
    global _active_slot
    if _active_slot == name:
        _active_slot = None


def tokenizers_from_llm(llm: Any) -> tuple[Callable[[str], list[int]], Callable[[list[int]], str]]:
    def tokenize(text: str) -> list[int]:
        return llm.tokenize(text.encode("utf-8"))

    def detokenize(token_ids: list[int]) -> str:
        return llm.detokenize(token_ids).decode("utf-8", errors="replace")

    return tokenize, detokenize


def load_retrieval_model() -> Any:
    from _jina_common import load_jina_text

    _acquire_slot("jina-retrieval")
    return load_jina_text("retrieval")


def embed_document(llm: Any, content: str) -> np.ndarray:
    from _jina_common import embed_text

    return embed_text(llm, f"Document: {content}")


def embed_query(llm: Any, query: str) -> np.ndarray:
    from _jina_common import embed_text

    return embed_text(llm, f"Query: {query}")


def release_model(llm: Any) -> None:
    close = getattr(llm, "close", None)
    if callable(close):
        close()
    del llm
    gc.collect()
    _release_slot("jina-retrieval")


def load_reranker() -> Any:
    from download_models2 import (
        expected_jina_reranker_path,
        expected_jina_reranker_projector_path,
    )
    from _jina_common import JinaReranker

    from app.core.config import get_settings

    settings = get_settings()
    _acquire_slot("jina-reranker")
    return JinaReranker(
        expected_jina_reranker_path(),
        expected_jina_reranker_projector_path(),
        n_ctx=settings.rerank_n_ctx,
        n_batch=settings.rerank_n_batch,
    )


def estimate_rerank_prompt_tokens(query: str, documents: list[str]) -> int:
    from _jina_common import estimate_rerank_prompt_tokens as _estimate

    return _estimate(query, documents)


def rerank_documents(reranker: Any, query: str, documents: list[str], top_n: int) -> list[Any]:
    return reranker.rerank(query, documents, top_n=top_n)


def release_reranker(reranker: Any) -> None:
    embed_llm = getattr(reranker, "_embed_llm", None)
    if embed_llm is not None:
        close = getattr(embed_llm, "close", None)
        if callable(close):
            close()
        reranker._embed_llm = None
        del embed_llm
    del reranker
    gc.collect()
    _release_slot("jina-reranker")
