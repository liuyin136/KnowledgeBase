"""Tests for GLiNER2 local loader."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from gliner2 import GLiNER2

from scripts.gliner2 import _gliner_common as gliner_common


def test_load_gliner2_uses_local_path(tmp_path: Path):
    model_dir = tmp_path / "GLiNER2"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}", encoding="utf-8")

    mock_extractor = MagicMock()
    with (
        patch.object(gliner_common, "expected_gliner2_path", return_value=model_dir),
        patch.object(GLiNER2, "from_pretrained", return_value=mock_extractor) as mock_from_pretrained,
    ):
        out = gliner_common.load_gliner2(map_location="cpu")

    assert out is mock_extractor
    mock_from_pretrained.assert_called_once_with(str(model_dir), map_location="cpu")
