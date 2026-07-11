from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services import jina_runtime


class _FakeLlama:
    def __init__(self) -> None:
        self.closed = False

    def tokenize(self, raw: bytes) -> list[int]:
        return list(range(len(raw)))

    def detokenize(self, token_ids: list[int]) -> bytes:
        return b"x" * len(token_ids)

    def close(self) -> None:
        self.closed = True


def test_tokenizers_from_llm_roundtrip():
    llm = _FakeLlama()
    tokenize, detokenize = jina_runtime.tokenizers_from_llm(llm)
    ids = tokenize("hello")
    assert ids == [0, 1, 2, 3, 4]
    assert detokenize(ids) == "xxxxx"


def test_no_lru_cache_on_tokenizer():
    assert not hasattr(jina_runtime, "_chunk_tokenizer_model")
    assert not hasattr(jina_runtime, "chunk_tokenizers")


def test_model_slot_blocks_second_load(monkeypatch):
    monkeypatch.setattr(jina_runtime, "_active_slot", "jina-retrieval")
    with pytest.raises(RuntimeError, match="GPU model slot busy"):
        jina_runtime.load_retrieval_model()


def test_release_model_calls_close(monkeypatch):
    monkeypatch.setattr(jina_runtime, "_active_slot", "jina-retrieval")
    llm = _FakeLlama()
    jina_runtime.release_model(llm)
    assert llm.closed
    assert jina_runtime._active_slot is None


def test_release_reranker_clears_embed_llm(monkeypatch):
    monkeypatch.setattr(jina_runtime, "_active_slot", "jina-reranker")
    embed_llm = _FakeLlama()
    reranker = MagicMock()
    reranker._embed_llm = embed_llm
    jina_runtime.release_reranker(reranker)
    assert embed_llm.closed
    assert jina_runtime._active_slot is None
