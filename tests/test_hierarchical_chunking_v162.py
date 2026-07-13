"""Unit tests for hierarchical chunking v1.62."""
from __future__ import annotations

from app.services.hierarchical_chunking import build_hierarchical_tree, split_grandchildren
from app.services.hierarchical_chunking import ChildRecord


def test_front_matter_excluded_from_parent_body():
    md = "---\ntitle: Meta\n---\n\n# Section\n\nHello world.\n"
    tree = build_hierarchical_tree(md)
    assert tree.front_matter.fields.get("title") == "Meta"
    assert tree.families
    assert all("title: Meta" not in p.content for p in tree.parents)
    assert tree.parents
    assert "Hello world" in tree.parents[0].content


def test_code_block_is_standalone_child():
    md = "# Sec\n\nIntro para long enough to stand alone as paragraph text.\n\n```python\nprint(1)\nprint(2)\n```\n\nAfter.\n"
    tree = build_hierarchical_tree(md)
    types = [c.block_type for c in tree.children]
    assert "code" in types
    code = next(c for c in tree.children if c.block_type == "code")
    assert "print(1)" in code.content


def test_code_grandchild_is_per_line():
    child = ChildRecord(
        id="p__c0",
        parent_id="p",
        child_index=0,
        content="```bash\necho a\necho b\n```",
        content_hash="h",
        token_count=4,
        block_type="code",
    )
    gcs = split_grandchildren(child)
    assert len(gcs) == 2
    assert gcs[0].content.strip() == "echo a"
    assert gcs[1].content.strip() == "echo b"


def test_table_skipped_for_grandchildren():
    child = ChildRecord(
        id="p__c0",
        parent_id="p",
        child_index=0,
        content="| a | b |\n| --- | --- |\n| 1 | 2 |",
        content_hash="h",
        token_count=6,
        block_type="table",
    )
    assert split_grandchildren(child) == []


def test_family_present_for_short_doc():
    md = "# A\n\nShort.\n"
    tree = build_hierarchical_tree(md)
    assert len(tree.families) == 1
    assert tree.parents[0].family_id == tree.families[0].id
