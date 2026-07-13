"""Tests for Qwen3-8B local loader."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.Qwen import _qwen_common as qwen_common


def test_load_qwen3_4bit_uses_local_path(tmp_path: Path):
    model_dir = tmp_path / "Qwen3-8B"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    (model_dir / "tokenizer.json").write_text("{}", encoding="utf-8")

    mock_tok = MagicMock()
    mock_model = MagicMock()
    with (
        patch.object(qwen_common, "expected_qwen3_path", return_value=model_dir),
        patch("transformers.AutoTokenizer.from_pretrained", return_value=mock_tok) as mock_tok_from,
        patch("transformers.AutoModelForCausalLM.from_pretrained", return_value=mock_model) as mock_model_from,
    ):
        tok, model = qwen_common.load_qwen3_4bit()

    assert tok is mock_tok
    assert model is mock_model
    mock_tok_from.assert_called_once_with(str(model_dir), local_files_only=True)
    mock_model_from.assert_called_once()
    assert mock_model_from.call_args.kwargs["quantization_config"] is not None
