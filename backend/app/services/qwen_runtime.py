"""Qwen3-8B lifecycle with shared GPU slot + VRAM guard."""
from __future__ import annotations

import gc
from typing import Any

from app.core.logging import get_logger
from app.services import jina_runtime
from app.services.gpu_utils import get_vram_used_mb

logger = get_logger("rag.gpu.qwen")

VRAM_BUDGET_MB = 7168
SLOT_NAME = "qwen3-8b"


def reset_gpu_slot() -> str | None:
    return jina_runtime.reset_gpu_slot()


def load_extract_model(**kwargs: Any) -> tuple[Any, Any]:
    reset_gpu_slot()
    vram_before = get_vram_used_mb()
    logger.info("qwen_vram_before_mb", vram_mb=vram_before)
    if vram_before > VRAM_BUDGET_MB:
        raise RuntimeError(
            f"VRAM already at {vram_before} MB before Qwen3 load (budget {VRAM_BUDGET_MB})"
        )

    jina_runtime.acquire_gpu_slot(SLOT_NAME)
    try:
        from scripts.Qwen._qwen_common import load_qwen3_4bit

        tokenizer, model = load_qwen3_4bit(**kwargs)
    except Exception:
        jina_runtime.release_gpu_slot(SLOT_NAME)
        raise

    vram_after = get_vram_used_mb()
    logger.info("qwen_vram_after_mb", vram_mb=vram_after)
    if vram_after > VRAM_BUDGET_MB:
        release_extract_model(model, tokenizer)
        raise RuntimeError(
            f"VRAM {vram_after} MB exceeds budget {VRAM_BUDGET_MB} after Qwen3 load"
        )
    return tokenizer, model


def release_extract_model(model: Any, tokenizer: Any | None = None) -> None:
    del model
    if tokenizer is not None:
        del tokenizer
    gc.collect()
    jina_runtime.release_gpu_slot(SLOT_NAME)
    logger.info("qwen_vram_released_mb", vram_mb=get_vram_used_mb())
