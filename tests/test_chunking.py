from __future__ import annotations

from app.services.chunking import chunk_document


def test_empty_document_returns_no_chunks():
    assert chunk_document("") == []
    assert chunk_document("   \n  ") == []


def test_single_window_when_under_max():
    text = "alpha beta gamma delta"
    chunks = chunk_document(text, chunk_token_max=100, overlap_tokens=10, stride_tokens=90)
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert "alpha" in chunks[0].content


def test_overlap_produces_multiple_chunks():
    tokens = [f"t{i}" for i in range(200)]
    text = " ".join(tokens)
    chunks = chunk_document(text, chunk_token_max=100, overlap_tokens=10, stride_tokens=90)
    assert len(chunks) >= 2
    assert chunks[0].chunk_index == 0
    assert chunks[1].chunk_index == 1


def test_tail_discarded_when_shorter_than_overlap():
    # 189 tokens → k=2 window has 9 tokens (< overlap 10), fully inside prev overlap tail
    tokens = [f"w{i}" for i in range(189)]
    text = " ".join(tokens)
    chunks = chunk_document(text, chunk_token_max=100, overlap_tokens=10, stride_tokens=90)
    assert len(chunks) == 2
    assert chunks[-1].token_count == 99


def test_production_tail_discard_produces_n_minus_one_chunks():
    """Plan Task 1.2: final window < 2950 tokens and fully overlapped → N-1 chunks."""
    chunk_token_max = 29500
    overlap_tokens = 2950
    stride_tokens = 26550
    # T = 55100 → raw windows at k=0,1,2; last has 2000 tokens (< 2950) and ⊆ prev tail
    total_tokens = 53100 + 2000
    tokens = [f"t{i}" for i in range(total_tokens)]
    text = " ".join(tokens)
    chunks = chunk_document(
        text,
        chunk_token_max=chunk_token_max,
        overlap_tokens=overlap_tokens,
        stride_tokens=stride_tokens,
    )
    assert len(chunks) == 2
    assert all(c.token_count <= chunk_token_max for c in chunks)
