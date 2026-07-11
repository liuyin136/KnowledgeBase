"""3-tier hierarchical chunking: Parent (AST) → Child (paragraph) → Grandchild (sentence)."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Callable

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from app.core.constants import CHUNK_TOKEN_MAX
from app.services.chunking import clean_text, content_hash

_HEADER_SPLITS = [("#", "h1"), ("##", "h2"), ("###", "h3")]
_MIN_PARAGRAPH_CHARS = 40


@dataclass
class ParentRecord:
    id: str
    parent_index: int
    content: str
    content_hash: str
    header_path: str
    token_count: int


@dataclass
class ChildRecord:
    id: str
    parent_id: str
    child_index: int
    content: str
    content_hash: str
    token_count: int
    parent_index: int = 0


@dataclass
class GrandchildRecord:
    id: str
    child_id: str
    parent_id: str
    grandchild_index: int
    content: str
    parent_index: int = 0
    child_index: int = 0


@dataclass
class HierarchicalTree:
    parents: list[ParentRecord] = field(default_factory=list)
    children: list[ChildRecord] = field(default_factory=list)
    grandchildren: list[GrandchildRecord] = field(default_factory=list)


@lru_cache(maxsize=1)
def _spacy_nlp():
    import spacy

    return spacy.load("en_core_web_sm")


def _count_tokens(text: str, tokenize: Callable[[str], list] | None) -> int:
    if tokenize is not None:
        return len(tokenize(text))
    return len(re.findall(r"\S+", text))


def _header_path_from_metadata(meta: dict) -> str:
    parts = [str(meta[k]) for k in ("h1", "h2", "h3") if meta.get(k)]
    return " > ".join(parts)


def split_parents_ast(md: str, *, source_file: str = "") -> list[ParentRecord]:
    del source_file  # reserved for future source-aware splitting
    cleaned = clean_text(md)
    if not cleaned:
        return []

    splitter = MarkdownHeaderTextSplitter(headers_to_split_on=_HEADER_SPLITS, strip_headers=False)
    docs = splitter.split_text(cleaned)
    if not docs:
        return [
            ParentRecord(
                id=str(uuid.uuid4()),
                parent_index=0,
                content=cleaned,
                content_hash=content_hash(cleaned),
                header_path="",
                token_count=len(re.findall(r"\S+", cleaned)),
            )
        ]

    parents: list[ParentRecord] = []
    for i, doc in enumerate(docs):
        text = (doc.page_content or "").strip()
        if not text:
            continue
        header_path = _header_path_from_metadata(getattr(doc, "metadata", {}) or {})
        parents.append(
            ParentRecord(
                id=str(uuid.uuid4()),
                parent_index=i,
                content=text,
                content_hash=content_hash(text),
                header_path=header_path,
                token_count=len(re.findall(r"\S+", text)),
            )
        )
    return parents


def _paragraph_parts(text: str) -> list[str]:
    # MarkdownHeaderTextSplitter often collapses blank lines into markdown hard breaks.
    text = re.sub(r"  \n", "\n\n", text)
    raw = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not raw:
        return [text.strip()] if text.strip() else []
    merged: list[str] = []
    buf = ""
    for part in raw:
        if len(part) < _MIN_PARAGRAPH_CHARS and buf:
            buf = f"{buf}\n\n{part}"
            continue
        if buf:
            merged.append(buf)
        buf = part
    if buf:
        merged.append(buf)
    return merged


def _hard_split_child(text: str, tokenize: Callable[[str], list] | None, detokenize: Callable[[list], str] | None) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_TOKEN_MAX, chunk_overlap=0)
    chunks = splitter.split_text(text)
    if tokenize is None or detokenize is None:
        return chunks
    out: list[str] = []
    for chunk in chunks:
        tokens = tokenize(chunk)
        if len(tokens) <= CHUNK_TOKEN_MAX:
            out.append(chunk)
        else:
            for i in range(0, len(tokens), CHUNK_TOKEN_MAX):
                out.append(detokenize(tokens[i : i + CHUNK_TOKEN_MAX]))
    return out


def split_children(
    parent: ParentRecord,
    *,
    tokenize: Callable[[str], list] | None = None,
    detokenize: Callable[[list], str] | None = None,
) -> list[ChildRecord]:
    paragraphs = _paragraph_parts(parent.content)
    child_texts: list[str] = []
    for para in paragraphs:
        if _count_tokens(para, tokenize) > CHUNK_TOKEN_MAX:
            child_texts.extend(_hard_split_child(para, tokenize, detokenize))
        else:
            child_texts.append(para)

    children: list[ChildRecord] = []
    for idx, text in enumerate(child_texts):
        text = text.strip()
        if not text:
            continue
        children.append(
            ChildRecord(
                id=f"{parent.id}__c{idx}",
                parent_id=parent.id,
                child_index=idx,
                content=text,
                content_hash=content_hash(text),
                token_count=_count_tokens(text, tokenize),
                parent_index=parent.parent_index,
            )
        )
    return children


def split_grandchildren(child: ChildRecord) -> list[GrandchildRecord]:
    text = child.content.strip()
    if not text:
        return []

    nlp = _spacy_nlp()
    doc = nlp(text)
    sentences = [s.text.strip() for s in doc.sents if s.text.strip()]
    if not sentences:
        sentences = [text]

    out: list[GrandchildRecord] = []
    for idx, sent in enumerate(sentences):
        out.append(
            GrandchildRecord(
                id=f"{child.parent_id}__c{child.child_index}__g{idx}",
                child_id=child.id,
                parent_id=child.parent_id,
                grandchild_index=idx,
                content=sent,
                parent_index=child.parent_index,
                child_index=child.child_index,
            )
        )
    return out


def build_hierarchical_tree(
    md: str,
    *,
    tokenize: Callable[[str], list] | None = None,
    detokenize: Callable[[list], str] | None = None,
) -> HierarchicalTree:
    parents = split_parents_ast(md)
    children: list[ChildRecord] = []
    grandchildren: list[GrandchildRecord] = []
    for parent in parents:
        for child in split_children(parent, tokenize=tokenize, detokenize=detokenize):
            children.append(child)
            grandchildren.extend(split_grandchildren(child))
    return HierarchicalTree(parents=parents, children=children, grandchildren=grandchildren)
