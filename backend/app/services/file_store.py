from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import aiofiles

from app.core.config import get_settings
from app.models.file_schemas import Category, CreateLogRequest, FileListItem
from app.services import file_cache

ALLOWED_EXTENSIONS = {".md", ".txt", ".sql", ".py"}
CATEGORY_DIRS: dict[Category, str] = {
    "RND": "RND",
    "Daily": "Daily",
    "case": "case",
}


class FileStoreError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def ensure_data_dirs() -> None:
    settings = get_settings()
    root = Path(settings.data_root)
    root.mkdir(parents=True, exist_ok=True)
    for subdir in CATEGORY_DIRS.values():
        (root / subdir).mkdir(parents=True, exist_ok=True)


def _data_root() -> Path:
    return Path(get_settings().data_root)


def slugify(title: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", title.strip().lower())
    slug = re.sub(r"[-\s]+", "-", slug).strip("-")
    return slug or "untitled"


def resolve_path(relative_path: str) -> Path:
    if not relative_path or relative_path.startswith("/") or ".." in relative_path.split("/"):
        raise FileStoreError("Invalid path", 403)

    parts = relative_path.split("/", 1)
    if len(parts) != 2:
        raise FileStoreError("Path must be category/filename", 400)

    category, filename = parts
    if category not in CATEGORY_DIRS:
        raise FileStoreError(f"Unknown category: {category}", 400)

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise FileStoreError(f"Extension not allowed: {ext}", 400)

    root = _data_root()
    target = (root / category / filename).resolve()
    allowed_root = (root / category).resolve()

    if not str(target).startswith(str(allowed_root)):
        raise FileStoreError("Path traversal detected", 403)

    return target


def relative_path_from_absolute(path: Path) -> str:
    root = _data_root().resolve()
    rel = path.resolve().relative_to(root)
    return rel.as_posix()


def render_log_content(body: CreateLogRequest, log_date: date | None = None) -> str:
    today = (log_date or date.today()).isoformat()
    title = body.title.strip()

    if body.category == "RND":
        return (
            f"# {today} | {title}\n"
            f"#Environment:\n{body.environment}\n"
            f"#Execution step:\n{body.execution_step}\n"
            f"#Results/Observation:\n{body.results}\n"
            f"#next steps\n{body.next_steps}\n"
        )

    if body.category == "case":
        return (
            f"# {today} | {title}\n"
            f"#Symptom\n{body.symptom}\n"
            f"#Error log\n{body.error_log}\n"
            f"#Investigation\n{body.investigation}\n"
            f"#solution:\n{body.solution}\n"
            f"#note:\n{body.note}\n"
        )

    return (
        f"# {today} | {title}\n"
        f"#Done\n{body.done}\n"
        f"#TODO\n{body.todo}\n"
        f"#Blocker:\n{body.blocker}\n"
    )


def _matches_filters(
    path: Path,
    keyword: str | None,
    filter_date: str | None,
) -> bool:
    name = path.name.lower()
    rel = relative_path_from_absolute(path)

    if filter_date:
        date_in_name = filter_date in name
        date_in_header = False
        if not date_in_name and path.suffix.lower() in {".md", ".txt"}:
            try:
                first_line = path.read_text(encoding="utf-8", errors="replace").split("\n", 1)[0]
                date_in_header = filter_date in first_line
            except OSError:
                pass
        if not date_in_name and not date_in_header:
            return False

    if keyword:
        kw = keyword.lower()
        if kw in name or kw in rel.lower():
            return True
        if path.suffix.lower() in {".md", ".txt", ".sql", ".py"}:
            try:
                content = path.read_text(encoding="utf-8", errors="replace").lower()
                return kw in content
            except OSError:
                return False
        return False

    return True


def list_files(
    category: Category | None = None,
    keyword: str | None = None,
    filter_date: str | None = None,
) -> list[FileListItem]:
    root = _data_root()
    categories: list[Category] = [category] if category else list(CATEGORY_DIRS.keys())
    results: list[FileListItem] = []

    for cat in categories:
        cat_dir = root / CATEGORY_DIRS[cat]
        if not cat_dir.is_dir():
            continue
        for path in sorted(cat_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not path.is_file():
                continue
            if path.suffix.lower() not in ALLOWED_EXTENSIONS:
                continue
            if not _matches_filters(path, keyword, filter_date):
                continue
            stat = path.stat()
            results.append(
                FileListItem(
                    path=relative_path_from_absolute(path),
                    name=path.name,
                    category=cat,
                    modified_at=stat.st_mtime,
                )
            )

    return results


async def read_content(relative_path: str) -> tuple[str, int]:
    path = resolve_path(relative_path)
    if not path.is_file():
        raise FileStoreError("File not found", 404)

    settings = get_settings()
    size = path.stat().st_size

    if size <= settings.file_cache_max_bytes:
        cached = file_cache.get_cached(relative_path)
        if cached is not None:
            return cached, size

        async with aiofiles.open(path, encoding="utf-8") as f:
            content = await f.read()

        file_cache.set_cached(relative_path, content)
        return content, size

    async with aiofiles.open(path, encoding="utf-8") as f:
        content = await f.read()
    return content, size


async def write_content(relative_path: str, content: str) -> None:
    path = resolve_path(relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(content)

    file_cache.invalidate(relative_path)
    file_cache.set_cached(relative_path, content)


async def create_log(body: CreateLogRequest) -> tuple[str, str]:
    today = date.today().isoformat()
    filename = f"{today}_{slugify(body.title)}.md"
    relative = f"{body.category}/{filename}"
    path = resolve_path(relative)

    if path.exists():
        raise FileStoreError("A log with this title already exists for today", 409)

    content = render_log_content(body)
    await write_content(relative, content)
    return relative, content
