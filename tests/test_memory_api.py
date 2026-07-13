"""Memory API contract tests (schemas + queue — no FastAPI import in worker)."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.models.memory_schemas import MemoryExtractRequest
from app.services.job_queue import enqueue_extract_memory_graph


def test_memory_extract_request_requires_grandchild_ids():
    with pytest.raises(Exception):
        MemoryExtractRequest(query_text="test", grandchild_ids=[])


def test_enqueue_extract_memory_graph():
    with patch("app.services.job_queue.get_queue") as mock_queue_fn:
        job = type("J", (), {"id": "job-1"})()
        mock_queue_fn.return_value.enqueue.return_value = job
        job_id = enqueue_extract_memory_graph(
            query_text="test",
            grandchild_ids=["g1"],
            span_id="span",
        )
    assert job_id == "job-1"


def test_enqueue_extract_memory_graph_rejects_empty():
    with pytest.raises(ValueError):
        enqueue_extract_memory_graph(query_text="test", grandchild_ids=[])
