from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Knowledge:
    id: str
    source_file: str
    title: str = ""
    category: str = ""
    token_count: int = 0
    chunk_count: int = 0
    indexed_at: datetime | None = None
    last_content_hash: str = ""
    mtime: float = 0.0


@dataclass
class KnowledgeChunk:
    id: str
    chunk_index: int
    content: str
    content_hash: str
    token_count: int
    start_token: int
    end_token: int
    vector: list[float] = field(default_factory=list)
    vector_coarse_256: list[float] = field(default_factory=list)
    vector_coarse_512: list[float] = field(default_factory=list)
    embedding_model: str = "jina-v5-omni-retrieval-gguf"
    indexed_at: datetime | None = None
    parent_source_file: str = ""


@dataclass
class KnowledgeParent:
    id: str
    parent_index: int
    content: str
    content_hash: str
    header_path: str
    source_file: str
    token_count: int


@dataclass
class KnowledgeChild:
    id: str
    parent_id: str
    child_index: int
    content: str
    content_hash: str
    token_count: int
    source_file: str
    vector: list[float] = field(default_factory=list)
    vector_coarse_256: list[float] = field(default_factory=list)
    vector_coarse_512: list[float] = field(default_factory=list)
    embedding_model: str = "jina-v5-omni-retrieval-gguf"
    indexed_at: datetime | None = None


@dataclass
class KnowledgeGrandchild:
    id: str
    child_id: str
    parent_id: str
    grandchild_index: int
    content: str
    source_file: str


@dataclass
class ChunkRecord:
    chunk_index: int
    content: str
    content_hash: str
    token_count: int
    start_token: int
    end_token: int


def node_to_dict(node: Any) -> dict[str, Any]:
    if node is None:
        return {}
    if isinstance(node, dict):
        return dict(node)
    if hasattr(node, "items"):
        return dict(node.items())
    return dict(node)
