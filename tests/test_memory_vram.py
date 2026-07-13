"""VRAM sequencing tests for extract runtime (Qwen3-8B)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services import jina_runtime, liquid_runtime


def test_reset_gpu_slot_clears_active_slot():
    jina_runtime._active_slot = "jina-retrieval"
    prev = jina_runtime.reset_gpu_slot()
    assert prev == "jina-retrieval"
    assert jina_runtime._active_slot is None


def test_load_extract_model_acquires_slot():
    tokenizer = MagicMock()
    model = MagicMock()
    with (
        patch("app.services.qwen_runtime.get_vram_used_mb", return_value=1000),
        patch("scripts.Qwen._qwen_common.load_qwen3_4bit", return_value=(tokenizer, model)),
        patch("app.services.jina_runtime.acquire_gpu_slot") as mock_acquire,
        patch("app.services.jina_runtime.release_gpu_slot"),
    ):
        out = liquid_runtime.load_extract_model()
    assert out == (tokenizer, model)
    mock_acquire.assert_called_once_with("qwen3-8b")
