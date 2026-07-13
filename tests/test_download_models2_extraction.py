"""Regression: GLiNER2/Qwen3 build download uses library from_pretrained, not snapshot_download."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from gliner2 import GLiNER2

import download_models2 as dm


def test_download_gliner2_uses_from_pretrained_and_save(tmp_path: Path):
    dest = tmp_path / "GLiNER2"
    mock_extractor = MagicMock()
    with (
        patch.object(GLiNER2, "from_pretrained", return_value=mock_extractor) as mock_from,
        patch.object(dm, "verify_pretrained_model_dir"),
    ):
        out = dm.download_gliner2_model(tmp_path)
    mock_from.assert_called_once_with(dm.GLINER2_REPO)
    mock_extractor.save_pretrained.assert_called_once_with(str(dest))
    assert out == dest


def test_download_qwen3_uses_auto_classes_and_save(tmp_path: Path):
    dest = tmp_path / "Qwen3-8B"
    mock_tok = MagicMock()
    mock_model = MagicMock()
    with (
        patch("transformers.AutoTokenizer.from_pretrained", return_value=mock_tok) as mock_tok_from,
        patch("transformers.AutoModelForCausalLM.from_pretrained", return_value=mock_model) as mock_model_from,
        patch.object(dm, "verify_pretrained_model_dir"),
    ):
        out = dm.download_qwen3_model(tmp_path)
    mock_tok_from.assert_called_once_with(dm.QWEN3_REPO)
    mock_model_from.assert_called_once_with(dm.QWEN3_REPO, low_cpu_mem_usage=True)
    mock_tok.save_pretrained.assert_called_once_with(dest)
    mock_model.save_pretrained.assert_called_once_with(dest)
    assert out == dest
