"""Shared helpers for LiquidAI GGUF draft scripts."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from llama_cpp import Llama

from download_models2 import LIQUID_MIN_BYTES, expected_liquid_path, verify_gguf_file

DATA_ROOT = Path("/data")
PIC_DIR = DATA_ROOT / "pic"


def require_liquid(model_key: str) -> Path:
    path = expected_liquid_path(model_key)
    try:
        verify_gguf_file(path, LIQUID_MIN_BYTES[model_key])
    except (FileNotFoundError, ValueError) as exc:
        print(f"Model not available: {exc}", file=sys.stderr)
        sys.exit(1)
    return path


def load_liquid(model_key: str, *, mmproj_key: str | None = None) -> Llama:
    """Load a LiquidAI GGUF from MODEL_PATH (never from_pretrained at runtime)."""
    path = require_liquid(model_key)
    kwargs: dict[str, Any] = {
        "model_path": str(path),
        "n_gpu_layers": -1,
        "n_ctx": 32768,
        "verbose": 0,
        "flash_attn": 1,
    }
    if mmproj_key is not None:
        mmproj = require_liquid(mmproj_key)
        # clip_model_path is the llama-cpp-python multimodal projector hook
        kwargs["clip_model_path"] = str(mmproj)
    print(f"Loading {path.name}...")
    return Llama(**kwargs)


def run_chat(llm: Llama, messages: list[dict[str, Any]], **kwargs: Any) -> str:
    """Thin create_chat_completion wrapper with Liquid-friendly defaults."""
    defaults: dict[str, Any] = {
        "temperature": 0.1,
        "top_p": 0.1,
        "top_k": 50,
        "repeat_penalty": 1.05,
        "max_tokens": 256,
    }
    defaults.update(kwargs)
    response = llm.create_chat_completion(messages=messages, **defaults)
    return response["choices"][0]["message"]["content"]
