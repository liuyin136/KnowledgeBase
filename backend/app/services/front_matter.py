"""Parse and strip Markdown front-matter (YAML or preamble before first header)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_HEADER_RE = re.compile(r"^#{1,6}\s+\S", re.MULTILINE)
_YAML_FENCE_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


@dataclass
class FrontMatterResult:
    body: str
    raw_yaml: str | None = None
    fields: dict[str, Any] = field(default_factory=dict)


def _parse_simple_yaml(raw: str) -> dict[str, Any]:
    """Minimal key: value YAML parser (no nested structures required)."""
    fields: dict[str, Any] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            fields[key] = value
    return fields


def strip_front_matter(md: str) -> FrontMatterResult:
    """
    Strip document metadata from the start of an MD file.

    Rules:
    - Prefer fenced YAML between --- ... --- at the start.
    - Otherwise treat all content before the first ATX header (# ...) as metadata.
    - If no header exists, treat leading blank/YAML-like block only when fenced.
    """
    text = md or ""
    if not text.strip():
        return FrontMatterResult(body="")

    # Fenced YAML at start (optional leading whitespace)
    stripped = text.lstrip("\ufeff")
    m = _YAML_FENCE_RE.match(stripped)
    if m:
        raw = m.group(1)
        body = stripped[m.end() :]
        return FrontMatterResult(body=body.lstrip("\n"), raw_yaml=raw, fields=_parse_simple_yaml(raw))

    # Content before first header is metadata
    header_match = _HEADER_RE.search(stripped)
    if header_match and header_match.start() > 0:
        raw = stripped[: header_match.start()].rstrip()
        body = stripped[header_match.start() :]
        if raw.strip():
            return FrontMatterResult(
                body=body,
                raw_yaml=raw if raw.strip() else None,
                fields=_parse_simple_yaml(raw),
            )

    return FrontMatterResult(body=stripped)
