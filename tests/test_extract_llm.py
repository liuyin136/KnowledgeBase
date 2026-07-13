
"""Tests for extract_llm adapter."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services import extract_llm


def test_run_extract_chat_delegates_to_qwen_common():
    tokenizer = MagicMock()
    model = MagicMock()
    with patch("scripts.Qwen._qwen_common.run_chat", return_value="ok") as mock_run:
        out = extract_llm.run_extract_chat(
            (tokenizer, model),
            [{"role": "user", "content": "hi"}],
            max_new_tokens=128,
        )
    assert out == "ok"
    mock_run.assert_called_once_with(
        tokenizer, model, [{"role": "user", "content": "hi"}], max_new_tokens=128
    )
