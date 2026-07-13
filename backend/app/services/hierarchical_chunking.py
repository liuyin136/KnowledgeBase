"""4-tier hierarchical chunking v1.62: Family → Parent → Child → Grandchild."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Callable, Literal

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from app.core.constants import CHUNK_TOKEN_MAX
from app.services.chunking import clean_text, content_hash
from app.services.front_matter import FrontMatterResult, strip_front_matter

_HEADER_SPLITS = [("#", "h1"), ("##", "h2"), ("###", "h3")]
_MIN_PARAGRAPH_CHARS = 40

BlockType = Literal["paragraph", "table", "code", "list", "mermaid"]


@dataclass
class FamilyRecord:
    id: str
    family_index: int
    content: str
    content_hash: str
    token_count: int


@dataclass
class ParentRecord:
    id: str
    parent_index: int
    content: str
    content_hash: str
    header_path: str
    token_count: int
    family_id: str = ""
    family_index: int = 0


@dataclass
class ChildRecord:
    id: str
    parent_id: str
    child_index: int
    content: str
    content_hash: str
    token_count: int
    parent_index: int = 0
    family_id: str = ""
    block_type: BlockType = "paragraph"


@dataclass
class GrandchildRecord:
    id: str
    child_id: str
    parent_id: str
    grandchild_index: int
    content: str
    content_hash: str = ""
    token_count: int = 0
    parent_index: int = 0
    child_index: int = 0


@dataclass
class HierarchicalTree:
    front_matter: FrontMatterResult = field(default_factory=FrontMatterResult)
    families: list[FamilyRecord] = field(default_factory=list)
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


def split_families(
    body: str,
    *,
    tokenize: Callable[[str], list] | None = None,
    detokenize: Callable[[list], str] | None = None,
) -> list[FamilyRecord]:
    """Split document body into Family siblings when over embed token limit."""
    cleaned = clean_text(body)
    if not cleaned:
        return []
    tokens_n = _count_tokens(cleaned, tokenize)
    if tokens_n <= CHUNK_TOKEN_MAX:
        return [
            FamilyRecord(
                id=str(uuid.uuid4()),
                family_index=0,
                content=cleaned,
                content_hash=content_hash(cleaned),
                token_count=tokens_n,
            )
        ]

    if tokenize is not None and detokenize is not None:
        tokens = tokenize(cleaned)
        chunks: list[str] = []
        for i in range(0, len(tokens), CHUNK_TOKEN_MAX):
            chunks.append(detokenize(tokens[i : i + CHUNK_TOKEN_MAX]))
    else:
        splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_TOKEN_MAX, chunk_overlap=0)
        chunks = splitter.split_text(cleaned)

    out: list[FamilyRecord] = []
    for idx, text in enumerate(chunks):
        text = text.strip()
        if not text:
            continue
        out.append(
            FamilyRecord(
                id=str(uuid.uuid4()),
                family_index=idx,
                content=text,
                content_hash=content_hash(text),
                token_count=_count_tokens(text, tokenize),
            )
        )
    return out or [
        FamilyRecord(
            id=str(uuid.uuid4()),
            family_index=0,
            content=cleaned,
            content_hash=content_hash(cleaned),
            token_count=tokens_n,
        )
    ]


def split_parents_ast(md: str, *, source_file: str = "", family_id: str = "") -> list[ParentRecord]:
    del source_file
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
                family_id=family_id,
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
                family_id=family_id,
            )
        )
    return parents


def _detect_block_type(text: str) -> BlockType:
    s = text.strip()
    if s.startswith("```mermaid") or s.startswith("~~~mermaid"):
        return "mermaid"
    if s.startswith("```") or s.startswith("~~~"):
        return "code"
    lines = [ln for ln in s.splitlines() if ln.strip()]
    if len(lines) >= 2 and "|" in lines[0] and re.search(r"\|?\s*-{3,}", lines[1]):
        return "table"
    if all(re.match(r"^(\s*[-*+]|\s*\d+\.)\s+", ln) for ln in lines[: min(3, len(lines))]):
        return "list"
    return "paragraph"


def _split_structural_blocks(text: str) -> list[tuple[BlockType, str]]:
    """Split markdown into structural blocks; never split mid fence/table."""
    lines = text.splitlines(keepends=True)
    blocks: list[tuple[BlockType, str]] = []
    buf: list[str] = []
    fence: str | None = None
    in_table = False

    def flush_para() -> None:
        nonlocal buf
        if not buf:
            return
        raw = "".join(buf).strip()
        buf = []
        if not raw:
            return
        # Split paragraphs on blank lines within accumulated prose
        for part in re.split(r"\n\s*\n", raw):
            part = part.strip()
            if part:
                blocks.append((_detect_block_type(part), part))

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if fence is None and (stripped.startswith("```") or stripped.startswith("~~~")):
            flush_para()
            fence = stripped[:3]
            fence_buf = [line]
            i += 1
            while i < len(lines):
                fence_buf.append(lines[i])
                if lines[i].strip().startswith(fence):
                    i += 1
                    break
                i += 1
            block = "".join(fence_buf).strip()
            blocks.append((_detect_block_type(block), block))
            fence = None
            continue

        # Table: consecutive lines with |
        if fence is None and "|" in line and not in_table:
            flush_para()
            table_buf = [line]
            i += 1
            while i < len(lines) and "|" in lines[i]:
                table_buf.append(lines[i])
                i += 1
            block = "".join(table_buf).strip()
            if block:
                blocks.append(("table", block))
            continue

        buf.append(line)
        i += 1

    flush_para()
    if not blocks and text.strip():
        blocks.append((_detect_block_type(text), text.strip()))
    return blocks


def _hard_split_child(
    text: str, tokenize: Callable[[str], list] | None, detokenize: Callable[[list], str] | None
) -> list[str]:
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
    structural = _split_structural_blocks(parent.content)
    child_parts: list[tuple[BlockType, str]] = []
    for btype, text in structural:
        if _count_tokens(text, tokenize) > CHUNK_TOKEN_MAX:
            # Truncated structure → standalone hard-split chunks keep same block_type
            for piece in _hard_split_child(text, tokenize, detokenize):
                child_parts.append((btype, piece))
        else:
            child_parts.append((btype, text))

    children: list[ChildRecord] = []
    for idx, (btype, text) in enumerate(child_parts):
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
                family_id=parent.family_id,
                block_type=btype,
            )
        )
    return children


def _chinese_sentence_split(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？；\n])", text)
    return [p.strip() for p in parts if p.strip()]


def _looks_chinese(text: str) -> bool:
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return cjk >= max(3, len(text) // 4)


def split_grandchildren(child: ChildRecord) -> list[GrandchildRecord]:
    text = child.content.strip()
    if not text:
        return []

    # Skip table / mermaid for grandchild split
    if child.block_type in ("table", "mermaid"):
        return []

    # Code / command → one line per grandchild
    if child.block_type == "code":
        lines = text.splitlines()
        # Drop fence lines
        lines = [ln for ln in lines if not ln.strip().startswith("```") and not ln.strip().startswith("~~~")]
        sentences = [ln for ln in lines if ln.strip()]
        if not sentences:
            return []
    elif _looks_chinese(text):
        sentences = _chinese_sentence_split(text)
    else:
        try:
            nlp = _spacy_nlp()
            doc = nlp(text)
            sentences = [s.text.strip() for s in doc.sents if s.text.strip()]
        except Exception:
            sentences = _chinese_sentence_split(text) if _looks_chinese(text) else [text]
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
                content_hash=content_hash(sent),
                token_count=len(re.findall(r"\S+", sent)),
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
    fm = strip_front_matter(md)
    families = split_families(fm.body, tokenize=tokenize, detokenize=detokenize)
    parents: list[ParentRecord] = []
    children: list[ChildRecord] = []
    grandchildren: list[GrandchildRecord] = []

    global_parent_idx = 0
    for fam in families:
        fam_parents = split_parents_ast(fam.content, family_id=fam.id)
        for p in fam_parents:
            p.parent_index = global_parent_idx
            p.family_id = fam.id
            p.family_index = fam.family_index
            global_parent_idx += 1
            parents.append(p)
            for child in split_children(p, tokenize=tokenize, detokenize=detokenize):
                children.append(child)
                grandchildren.extend(split_grandchildren(child))

    return HierarchicalTree(
        front_matter=fm,
        families=families,
        parents=parents,
        children=children,
        grandchildren=grandchildren,
    )
