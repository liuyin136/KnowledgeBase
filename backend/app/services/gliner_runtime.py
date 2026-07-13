"""GLiNER2 model lifecycle (CPU-friendly; no GPU slot)."""
from __future__ import annotations

import gc
from typing import Any

from app.core.logging import get_logger

logger = get_logger("rag.gliner")


def load_gliner2_model(*, map_location: str = "cuda") -> Any:
    from scripts.gliner2._gliner_common import load_gliner2

    logger.info("gliner2_load_start", map_location=map_location)
    extractor = load_gliner2(map_location=map_location)  # type: ignore[arg-type]
    logger.info("gliner2_load_done")
    return extractor


def release_gliner2_model(extractor: Any) -> None:
    del extractor
    gc.collect()
    logger.info("gliner2_released")
