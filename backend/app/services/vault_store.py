"""Filesystem + SQLite operations for the RAG Content Vault."""
from __future__ import annotations

import hashlib
import math
import re
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from app.core.config import get_settings
from app.models.vault_schemas import (
    FolderRenamePreview,
    FolderRenamePreviewFile,
    PaginatedFilesResponse,
    VaultFile,
    VaultFolder,
)
from app.services import vault_db

MUTABLE_EXTENSIONS = {".md", ".txt"}
ALLOWED_EXTENSIONS = {".md", ".txt"}
OnConflict = Literal["replace", "fail"]
PREVIEW_MAX_CHARS = 240


@dataclass(frozen=True)
class WriteFileResult:
    file: VaultFile
    replaced: bool


class VaultStoreError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def slugify(title: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", title.strip().lower())
    slug = re.sub(r"[-\s]+", "-", slug).strip("-")
    return slug or "untitled"


def _vault_root() -> Path:
    return Path(get_settings().vault_root)


def resolve_vault_path(relative_path: str) -> Path:
    if not relative_path or relative_path.startswith("/") or ".." in relative_path.split("/"):
        raise VaultStoreError("Invalid path", 403)
    root = _vault_root().resolve()
    target = (root / relative_path).resolve()
    if not str(target).startswith(str(root)):
        raise VaultStoreError("Path traversal detected", 403)
    return target


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def row_to_vault_file(
    row: dict[str, Any],
    *,
    content_preview: str | None = None,
) -> VaultFile:
    return VaultFile(
        id=row["id"],
        folder_id=row["folder_id"],
        filename=row["filename"],
        relative_path=row["relative_path"],
        source=row["source"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        size_bytes=int(row["size_bytes"]),
        mime_ext=row["mime_ext"],
        mutable=bool(row["mutable"]),
        index_status=row["index_status"],
        chunk_count=int(row["chunk_count"] or 0),
        last_ingest_job_id=row.get("last_ingest_job_id"),
        last_ingest_at=row.get("last_ingest_at"),
        ingest_locked=bool(row.get("ingest_lock_job_id")),
        error_message=row.get("error_message") or None,
        content_preview=content_preview,
    )


def row_to_vault_folder(row: dict[str, Any], *, file_count: int | None = None) -> VaultFolder:
    count = file_count if file_count is not None else vault_db.count_files_in_folder(row["id"])
    return VaultFolder(
        id=row["id"],
        name=row["name"],
        slug=row["slug"],
        created_at=row["created_at"],
        relative_path=row["relative_path"],
        file_count=count,
    )


def list_folders() -> list[VaultFolder]:
    return [row_to_vault_folder(r) for r in vault_db.list_folders()]


def _rename_block_reason(folder_id: str, folder: dict[str, Any], new_slug: str) -> str | None:
    if vault_db.folder_has_locked_files(folder_id):
        return "Folder has files being ingested"
    existing = vault_db.get_folder_by_slug(new_slug)
    if existing and existing["id"] != folder_id:
        return f"Folder slug already exists: {new_slug}"
    if new_slug != folder["slug"]:
        new_dir = resolve_vault_path(new_slug)
        if new_dir.exists():
            return "Target folder directory already exists"
        old_dir = resolve_vault_path(folder["slug"])
        if not old_dir.exists():
            return "Folder directory missing on disk"
    return None


def preview_folder_rename(folder_id: str, name: str) -> FolderRenamePreview:
    folder = vault_db.get_folder_by_id(folder_id)
    if not folder:
        raise VaultStoreError("Folder not found", 404)

    new_slug = slugify(name)
    old_slug = folder["slug"]
    slug_unchanged = new_slug == old_slug
    old_prefix = f"{old_slug}/"
    new_prefix = f"{new_slug}/"
    files = vault_db.list_files_in_folder(folder_id)
    block_reason = _rename_block_reason(folder_id, folder, new_slug)

    neo_count = 0
    if not slug_unchanged:
        try:
            from app.services.neo4j_client import get_neo4j_client

            neo_count = get_neo4j_client().count_knowledge_by_prefix(old_prefix)
        except Exception:
            neo_count = 0

    preview_rows: list[FolderRenamePreviewFile] = []
    for row in files[:10]:
        old_rel = row["relative_path"]
        new_rel = old_rel if slug_unchanged else new_prefix + old_rel[len(old_prefix) :]
        preview_rows.append(
            FolderRenamePreviewFile(
                old_relative_path=old_rel,
                new_relative_path=new_rel,
                index_status=row["index_status"],
            )
        )

    return FolderRenamePreview(
        folder_id=folder_id,
        old_name=folder["name"],
        new_name=name.strip(),
        old_slug=old_slug,
        new_slug=new_slug,
        slug_unchanged=slug_unchanged,
        can_rename=block_reason is None,
        block_reason=block_reason,
        total_files=len(files),
        neo4j_knowledge_count=neo_count,
        preview_files=preview_rows,
        has_more_files=len(files) > 10,
    )


def create_folder(name: str) -> VaultFolder:
    slug = slugify(name)
    if vault_db.get_folder_by_slug(slug):
        raise VaultStoreError(f"Folder slug already exists: {slug}", 409)
    relative_path = f"{slug}/"
    disk_path = resolve_vault_path(slug)
    disk_path.mkdir(parents=True, exist_ok=False)
    row = vault_db.insert_folder(
        folder_id=str(uuid.uuid4()),
        name=name.strip(),
        slug=slug,
        relative_path=relative_path,
    )
    return row_to_vault_folder(row)


def rename_folder(folder_id: str, name: str) -> VaultFolder:
    folder = vault_db.get_folder_by_id(folder_id)
    if not folder:
        raise VaultStoreError("Folder not found", 404)
    new_slug = slugify(name)
    existing = vault_db.get_folder_by_slug(new_slug)
    if existing and existing["id"] != folder_id:
        raise VaultStoreError(f"Folder slug already exists: {new_slug}", 409)

    old_slug = folder["slug"]
    if new_slug == old_slug:
        updated = vault_db.update_folder(folder_id, name=name.strip())
        return row_to_vault_folder(updated)  # type: ignore[arg-type]

    block_reason = _rename_block_reason(folder_id, folder, new_slug)
    if block_reason:
        raise VaultStoreError(block_reason, 409)

    old_prefix = f"{old_slug}/"
    new_prefix = f"{new_slug}/"

    try:
        from app.core.exceptions import Neo4jError
        from app.services.neo4j_client import get_neo4j_client

        get_neo4j_client().rename_knowledge_by_folder_prefix(old_slug, new_slug)
    except Neo4jError as exc:
        raise VaultStoreError(str(exc), 409) from exc

    old_dir = resolve_vault_path(old_slug)
    new_dir = resolve_vault_path(new_slug)
    if new_dir.exists():
        raise VaultStoreError("Target folder directory already exists", 409)
    if not old_dir.exists():
        raise VaultStoreError("Folder directory missing on disk", 404)

    old_dir.rename(new_dir)
    vault_db.update_file_paths_prefix(old_prefix, new_prefix)
    updated = vault_db.update_folder(
        folder_id,
        name=name.strip(),
        slug=new_slug,
        relative_path=f"{new_slug}/",
    )
    return row_to_vault_folder(updated)  # type: ignore[arg-type]


def delete_folder(folder_id: str) -> None:
    folder = vault_db.get_folder_by_id(folder_id)
    if not folder:
        raise VaultStoreError("Folder not found", 404)
    if vault_db.count_files_in_folder(folder_id) > 0:
        raise VaultStoreError("Folder not empty", 409)
    disk_path = resolve_vault_path(folder["slug"])
    if disk_path.exists():
        try:
            disk_path.rmdir()
        except OSError as exc:
            raise VaultStoreError(f"Cannot remove folder directory: {exc}", 409) from exc
    vault_db.delete_folder_row(folder_id)


def _require_unlocked(row: dict[str, Any]) -> None:
    if row.get("ingest_lock_job_id"):
        raise VaultStoreError("File is locked while ingest is running", 409)


def read_file_preview(relative_path: str, max_chars: int = PREVIEW_MAX_CHARS) -> str | None:
    try:
        path = resolve_vault_path(relative_path)
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8")
        text = text.replace("\r\n", "\n").strip()
        if not text:
            return None
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "…"
    except (OSError, UnicodeDecodeError, VaultStoreError):
        return None


def replace_file_content(
    file_id: str,
    content: str,
    *,
    source: str | None = None,
) -> VaultFile:
    row = vault_db.get_file_by_id(file_id)
    if not row:
        raise VaultStoreError("File not found", 404)
    _require_unlocked(row)

    path = resolve_vault_path(row["relative_path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    data = content.encode("utf-8")
    path.write_bytes(data)
    stat = path.stat()
    content_hash = _sha256_bytes(data)
    prev_status = row["index_status"]

    if prev_status == "deleted":
        new_status = "not_indexed"
        chunk_count = 0
    elif prev_status == "indexed":
        try:
            from app.services.neo4j_client import get_neo4j_client

            get_neo4j_client().delete_knowledge_by_source(row["relative_path"])
        except Exception:
            pass
        new_status = "modified"
        chunk_count = int(row.get("chunk_count") or 0)
    else:
        new_status = prev_status
        chunk_count = int(row.get("chunk_count") or 0)

    fields: dict[str, Any] = {
        "size_bytes": len(data),
        "mtime": stat.st_mtime,
        "content_hash": content_hash,
        "index_status": new_status,
        "updated_at": vault_db.utc_now(),
        "error_message": None,
        "chunk_count": chunk_count,
    }
    if source is not None:
        fields["source"] = source

    updated = vault_db.update_file_fields(file_id, **fields)
    return row_to_vault_file(updated)  # type: ignore[arg-type]


def create_text_file(
    *,
    folder_id: str,
    filename: str,
    content: str = "",
    source: str = "created",
    on_conflict: OnConflict = "replace",
) -> WriteFileResult:
    folder = vault_db.get_folder_by_id(folder_id)
    if not folder:
        raise VaultStoreError("Folder not found", 404)

    safe_name = Path(filename).name
    if safe_name != filename or "/" in filename or "\\" in filename:
        raise VaultStoreError("Invalid filename", 400)
    ext = Path(safe_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise VaultStoreError(f"Extension not allowed: {ext}", 400)

    relative_path = f"{folder['slug']}/{safe_name}"
    existing = vault_db.get_file_by_path(relative_path)
    if existing:
        if on_conflict == "fail":
            raise VaultStoreError("File already exists", 409)
        replaced = replace_file_content(existing["id"], content, source=source)
        return WriteFileResult(file=replaced, replaced=True)

    path = resolve_vault_path(relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = content.encode("utf-8")
    path.write_bytes(data)
    stat = path.stat()
    now = vault_db.utc_now()
    try:
        row = vault_db.insert_file(
            {
                "id": str(uuid.uuid4()),
                "folder_id": folder_id,
                "filename": safe_name,
                "relative_path": relative_path,
                "source": source,
                "created_at": now,
                "updated_at": now,
                "size_bytes": len(data),
                "mtime": stat.st_mtime,
                "content_hash": _sha256_bytes(data),
                "mime_ext": ext,
                "mutable": 1 if ext in MUTABLE_EXTENSIONS else 0,
                "index_status": "not_indexed",
                "chunk_count": 0,
                "last_ingest_job_id": None,
                "last_ingest_at": None,
                "ingest_lock_job_id": None,
                "error_message": None,
            }
        )
    except sqlite3.IntegrityError:
        raced = vault_db.get_file_by_path(relative_path)
        if not raced:
            raise
        if on_conflict == "fail":
            raise VaultStoreError("File already exists", 409) from None
        replaced = replace_file_content(raced["id"], content, source=source)
        return WriteFileResult(file=replaced, replaced=True)
    return WriteFileResult(file=row_to_vault_file(row), replaced=False)


def upload_file(
    *,
    folder_id: str,
    filename: str,
    data: bytes,
    on_conflict: OnConflict = "replace",
) -> WriteFileResult:
    text = data.decode("utf-8")
    return create_text_file(
        folder_id=folder_id,
        filename=filename,
        content=text,
        source="upload",
        on_conflict=on_conflict,
    )


def get_file(file_id: str) -> VaultFile:
    row = vault_db.get_file_by_id(file_id)
    if not row or row["index_status"] == "deleted":
        raise VaultStoreError("File not found", 404)
    return row_to_vault_file(row)


def read_file_content(file_id: str) -> str:
    row = vault_db.get_file_by_id(file_id)
    if not row or row["index_status"] == "deleted":
        raise VaultStoreError("File not found", 404)
    path = resolve_vault_path(row["relative_path"])
    if not path.is_file():
        raise VaultStoreError("File missing on disk", 404)
    return path.read_text(encoding="utf-8")


def save_file_content(file_id: str, content: str) -> VaultFile:
    row = vault_db.get_file_by_id(file_id)
    if not row or row["index_status"] == "deleted":
        raise VaultStoreError("File not found", 404)
    if not row["mutable"]:
        raise VaultStoreError("File is not mutable", 409)
    return replace_file_content(file_id, content)


def delete_file(file_id: str, *, purge_neo4j: bool = True) -> None:
    row = vault_db.get_file_by_id(file_id)
    if not row or row["index_status"] == "deleted":
        raise VaultStoreError("File not found", 404)
    _require_unlocked(row)

    path = resolve_vault_path(row["relative_path"])
    if path.is_file():
        path.unlink()
    if purge_neo4j:
        try:
            from app.services.neo4j_client import get_neo4j_client

            get_neo4j_client().delete_knowledge_by_source(row["relative_path"])
        except Exception:
            pass
    vault_db.delete_file_row(file_id)


def list_files(
    *,
    folder_id: str | None = None,
    keyword: str | None = None,
    index_status: str | None = None,
    page: int = 1,
    page_size: int = 10,
) -> PaginatedFilesResponse:
    rows, total = vault_db.list_files_paginated(
        folder_id=folder_id,
        keyword=keyword,
        index_status=index_status,
        page=page,
        page_size=page_size,
    )
    files = [
        row_to_vault_file(
            r,
            content_preview=read_file_preview(r["relative_path"]),
        )
        for r in rows
    ]
    total_pages = max(1, math.ceil(total / page_size)) if total else 0
    return PaginatedFilesResponse(
        files=files,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


def resolve_ingest_file(relative_path: str) -> tuple[Path, str]:
    """Resolve vault or legacy path. Prefer vault if the file exists there."""
    settings = get_settings()
    vault_candidate = Path(settings.vault_root) / relative_path
    if vault_candidate.is_file():
        return vault_candidate.resolve(), "vault"
    legacy = Path(settings.data_root) / relative_path
    if legacy.is_file():
        return legacy.resolve(), "legacy"
    # Prefer vault path for error messaging when row exists in SQLite
    if vault_db.get_file_by_path(relative_path):
        return vault_candidate.resolve(), "vault"
    return legacy.resolve(), "legacy"


def compute_file_hash(path: Path) -> str:
    return _sha256_file(path)
