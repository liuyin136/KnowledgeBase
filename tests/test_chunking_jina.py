from __future__ import annotations

from app.services.chunking import chunk_document, clean_text


def test_jina_tokenizer_changes_chunk_boundaries():
    text = clean_text("Hello world " * 500)

    regex_chunks = chunk_document(text, chunk_token_max=200, overlap_tokens=20, stride_tokens=180)
    assert len(regex_chunks) >= 2

    def fake_jina_tokenize(raw: str) -> list[int]:
        ids: list[int] = []
        for i, _word in enumerate(raw.split()):
            ids.extend([i * 2, i * 2 + 1])
        return ids

    def fake_jina_detokenize(ids: list[int]) -> str:
        return " ".join(f"t{i}" for i in ids)

    jina_chunks = chunk_document(
        text,
        tokenize=fake_jina_tokenize,
        detokenize=fake_jina_detokenize,
        chunk_token_max=200,
        overlap_tokens=20,
        stride_tokens=180,
    )
    assert len(jina_chunks) > len(regex_chunks)
