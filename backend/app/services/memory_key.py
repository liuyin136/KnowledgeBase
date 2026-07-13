"""Deterministic LWW identity for manual memory saves."""
from __future__ import annotations

import hashlib
import uuid


def source_query_id(query_text: str, user_query_id: str | None = None) -> str:
    if user_query_id:
        return user_query_id
    return hashlib.sha256(query_text.strip().encode("utf-8")).hexdigest()[:32]


def compute_memory_key(source_query_id: str, grandchild_ids: list[str]) -> str:
    sorted_ids = ",".join(sorted(grandchild_ids))
    payload = f"{source_query_id}:{sorted_ids}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def new_memory_id() -> str:
    return str(uuid.uuid4())
