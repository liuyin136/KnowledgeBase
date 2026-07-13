"""Shared helpers for Qwen/Qwen3-8B local loading with 4-bit bitsandbytes."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

from download_models2 import expected_qwen3_path, verify_pretrained_model_dir


def require_qwen3() -> Path:
    path = expected_qwen3_path()
    try:
        verify_pretrained_model_dir(path, require_tokenizer=True)
    except FileNotFoundError as exc:
        print(f"Qwen3-8B model not available: {exc}", file=sys.stderr)
        sys.exit(1)
    return path


def qwen3_bnb_config() -> BitsAndBytesConfig:
    return BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )


def load_qwen3_4bit(**kwargs: Any) -> tuple[AutoTokenizer, AutoModelForCausalLM]:
    """Load Qwen3-8B from MODEL_PATH/Qwen3-8B with 4-bit quantization (never hub id at runtime)."""
    path = require_qwen3()
    print(f"Loading Qwen3-8B (4-bit) from {path}...")
    tokenizer = AutoTokenizer.from_pretrained(str(path),local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        str(path),
        quantization_config=kwargs.pop("quantization_config", qwen3_bnb_config()),
        device_map=kwargs.pop("device_map", "auto"),
        local_files_only=True,
        **kwargs
    )
    return tokenizer, model


def run_chat(
    tokenizer: AutoTokenizer,
    model: AutoModelForCausalLM,
    messages: list[dict[str, str]],
    *,
    max_new_tokens: int = 256,
    enable_thinking: bool = False,
    **kwargs: Any,
) -> str:
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=enable_thinking,
    )
    inputs = tokenizer([text], return_tensors="pt").to(model.device)
    output_ids = model.generate(**inputs, max_new_tokens=max_new_tokens, temperature=0.7, top_p=0.8,top_k=20,min_p=0.0,**kwargs)
    new_tokens = output_ids[0][len(inputs.input_ids[0]) :].tolist()

    if enable_thinking:
        try:
            index = len(new_tokens) - new_tokens[::-1].index(151668)
        except ValueError:
            index = 0
        return tokenizer.decode(new_tokens[index:], skip_special_tokens=True).strip()

    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
