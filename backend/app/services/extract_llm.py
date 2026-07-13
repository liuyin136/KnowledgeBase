"""Qwen3 extract LLM chat adapter for GraphRAG memory extraction."""
from __future__ import annotations

from typing import Any

ExtractLlm = tuple[Any, Any]


def run_extract_chat(
    llm: ExtractLlm,
    messages: list[dict[str, str]],
    *,
    max_new_tokens: int = 256,
) -> str:
    """Run chat completion on Qwen3 (tokenizer, model) from qwen_runtime.load_extract_model."""
    if not isinstance(llm, tuple) or len(llm) != 2:
        raise TypeError("extract LLM must be (tokenizer, model) from load_extract_model")
    tokenizer, model = llm
    from scripts.Qwen._qwen_common import run_chat

    return run_chat(tokenizer, model, messages, max_new_tokens=max_new_tokens)
