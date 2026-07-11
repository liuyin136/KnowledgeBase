"""Resolve vault file paths for scoped hybrid search."""
from __future__ import annotations

from datetime import date, datetime, time, timezone

from app.services import vault_db

MAX_ALLOWLIST_PATHS = 500


class AllowlistTooLargeError(Exception):
    """Raised when scoped search matches more than MAX_ALLOWLIST_PATHS files."""


def _date_start_iso(d: date) -> str:
    return datetime.combine(d, time.min, tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _date_end_iso(d: date) -> str:
    return datetime.combine(d, time(23, 59, 59), tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_search_allowlist(
    folder_ids: list[str] | None,
    created_after: date | None,
    created_before: date | None,
    indexed_only: bool,
) -> list[str]:
    """Return relative_path allowlist for vault-scoped search."""
    clauses = ["index_status != 'deleted'"]
    params: list[object] = []

    if folder_ids is not None:
        if not folder_ids:
            return []
        placeholders = ",".join("?" * len(folder_ids))
        clauses.append(f"folder_id IN ({placeholders})")
        params.extend(folder_ids)

    if indexed_only:
        clauses.append("index_status = 'indexed'")

    if created_after is not None:
        clauses.append("created_at >= ?")
        params.append(_date_start_iso(created_after))

    if created_before is not None:
        clauses.append("created_at <= ?")
        params.append(_date_end_iso(created_before))

    sql = (
        "SELECT relative_path FROM vault_files WHERE "
        + " AND ".join(clauses)
        + " LIMIT ?"
    )
    params.append(MAX_ALLOWLIST_PATHS + 1)

    with vault_db.get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()

    if len(rows) > MAX_ALLOWLIST_PATHS:
        raise AllowlistTooLargeError(
            f"Scope matches more than {MAX_ALLOWLIST_PATHS} files; narrow your filters"
        )

    return [str(row["relative_path"]) for row in rows]
