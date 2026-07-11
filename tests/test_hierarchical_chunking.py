from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.hierarchical_chunking import (
    build_hierarchical_tree,
    split_children,
    split_parents_ast,
)


def test_split_parents_ast_headers():
    md = "# Title\n\nIntro\n\n## Section A\n\nParagraph one.\n\n## Section B\n\nParagraph two."
    parents = split_parents_ast(md)
    assert len(parents) >= 2
    assert any("Section A" in p.header_path or "Title" in p.content for p in parents)


def test_split_children_paragraphs():
    md = (
        "# Doc\n\n"
        "This is paragraph one with enough characters to avoid tiny-paragraph merge.\n\n"
        "This is paragraph two with enough characters to avoid tiny-paragraph merge.\n\n"
        "This is paragraph three with enough characters to avoid tiny-paragraph merge."
    )
    parents = split_parents_ast(md)
    assert parents
    children = split_children(parents[0])
    assert len(children) >= 2
    assert all(c.parent_id == parents[0].id for c in children)


def test_oversized_child_hard_split():
    long_para = "word " * 50000
    md = f"# Doc\n\n{long_para}"
    parents = split_parents_ast(md)
    assert parents
    tokenize = lambda t: t.split()
    detokenize = lambda toks: " ".join(toks)
    children = split_children(parents[0], tokenize=tokenize, detokenize=detokenize)
    assert len(children) > 1


def test_grandchild_mapping_mock_spacy():
    fake_nlp = MagicMock()
    sent_a = MagicMock()
    sent_a.text = "First sentence."
    sent_b = MagicMock()
    sent_b.text = "Second sentence."
    fake_doc = MagicMock()
    fake_doc.sents = [sent_a, sent_b]
    fake_nlp.return_value = fake_doc

    md = "# Hi\n\nFirst sentence. Second sentence."
    with patch("app.services.hierarchical_chunking._spacy_nlp", return_value=fake_nlp):
        tree = build_hierarchical_tree(md)
    assert tree.children
    assert len(tree.grandchildren) >= 2
    for g in tree.grandchildren:
        assert g.child_id
        assert g.parent_id == tree.children[0].parent_id
