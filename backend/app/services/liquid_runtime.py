"""Extract-model lifecycle — delegates to Qwen3-8B runtime (Phase 2.01 prep)."""
from __future__ import annotations

from typing import Any

from app.services import qwen_runtime


def reset_gpu_slot() -> str | None:
    return qwen_runtime.reset_gpu_slot()


def load_extract_model(**kwargs: Any) -> Any:
    return qwen_runtime.load_extract_model(**kwargs)


def release_extract_model(llm: Any, tokenizer: Any | None = None) -> None:
    if isinstance(llm, tuple) and len(llm) == 2:
        tokenizer, model = llm
        qwen_runtime.release_extract_model(model, tokenizer)
        return
    qwen_runtime.release_extract_model(llm, tokenizer)
