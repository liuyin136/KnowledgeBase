"""Lightweight ingest token estimates without GPU embed (Phase 1.7).

Runs on the slim backend service — no langchain/spaCy imports.
"""
from __future__ import annotations

import re

from app.core.constants import CHUNK_TOKEN_MAX
from app.services import vault_db
from app.services.chunking import clean_text
from app.services.front_matter import strip_front_matter
from app.services.vault_store import VaultStoreError, resolve_vault_path


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def estimate_tokens_from_text(md: str) -> int:
    """Approximate embed workload from body size and family splits (no GPU)."""
    fm = strip_front_matter(md)
    body = clean_text(fm.body)
    if not body:
        return 0
    base = _word_count(body)
    families = max(1, (base + CHUNK_TOKEN_MAX - 1) // CHUNK_TOKEN_MAX)
    # Proxy: family + parent + child + grandchild embed passes (~3× body per family).
    return base + families * base * 3


def estimate_file_tokens(file_id: str) -> tuple[int, str]:
    row = vault_db.get_file_by_id(file_id)
    if not row or row["index_status"] == "deleted":
        raise VaultStoreError("File not found", 404)
    path = resolve_vault_path(row["relative_path"])
    if not path.is_file():
        raise VaultStoreError("File missing on disk", 404)
    text = path.read_text(encoding="utf-8")
    return estimate_tokens_from_text(text), row["relative_path"]


def preview_ingest_files(file_ids: list[str]) -> list[dict]:
    items: list[dict] = []
    for file_id in file_ids:
        row = vault_db.get_file_by_id(file_id)
        if not row or row["index_status"] == "deleted":
            items.append(
                {
                    "file_id": file_id,
                    "relative_path": "",
                    "estimated_tokens": 0,
                    "ingestible": False,
                    "block_reason": "File not found",
                }
            )
            continue
        if row.get("ingest_lock_job_id"):
            items.append(
                {
                    "file_id": file_id,
                    "relative_path": row["relative_path"],
                    "estimated_tokens": 0,
                    "ingestible": False,
                    "block_reason": "Ingest already in progress",
                }
            )
            continue
        try:
            tokens, _ = estimate_file_tokens(file_id)
            items.append(
                {
                    "file_id": file_id,
                    "relative_path": row["relative_path"],
                    "estimated_tokens": tokens,
                    "ingestible": True,
                    "block_reason": None,
                }
            )
        except VaultStoreError as exc:
            items.append(
                {
                    "file_id": file_id,
                    "relative_path": row["relative_path"],
                    "estimated_tokens": 0,
                    "ingestible": False,
                    "block_reason": str(exc),
                }
            )
    return items
