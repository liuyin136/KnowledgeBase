"""Unit tests for front-matter stripping."""
from __future__ import annotations

from app.services.front_matter import strip_front_matter


def test_fenced_yaml_front_matter():
    md = "---\ntitle: Hello\nauthor: me\n---\n\n# Header\n\nBody text.\n"
    result = strip_front_matter(md)
    assert result.fields.get("title") == "Hello"
    assert result.fields.get("author") == "me"
    assert result.body.startswith("# Header")
    assert "title:" not in result.body


def test_preamble_before_header_as_metadata():
    md = "title: Draft\nstatus: wip\n\n# Real Header\n\nContent\n"
    result = strip_front_matter(md)
    assert result.body.startswith("# Real Header")
    assert "Draft" not in result.body
    assert result.fields.get("title") == "Draft"


def test_no_metadata_passthrough():
    md = "# Only Header\n\nHello\n"
    result = strip_front_matter(md)
    assert result.body.startswith("# Only Header")
    assert result.raw_yaml is None
    assert result.fields == {}
