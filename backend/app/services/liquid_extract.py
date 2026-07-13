"""Liquid extraction + structured JSON/YAML parsing for GraphRAG memory."""
from __future__ import annotations

import json
import re
from typing import Any

import yaml

from app.models.graph_memory_schemas import (
    ExtractClaim,
    ExtractEntity,
    ExtractRelation,
    GraphExtractResult,
)

_EXTRACT_PROMPT = """Extract a knowledge graph from the search context below.
Return a single JSON object only (no markdown fences, no YAML).
Keys: summary (string), entities (array), relations (array), claims (array).

entities items: {{"id": "...", "name": "...", "type": "..."}}
relations items: {{"source_id": "...", "target_id": "...", "type": "...", "weight": 0.0}}
claims items: {{"id": "...", "text": "...", "entity_id": "...", "confidence": 0.0, "grandchild_id": "..."}}

Escape all special characters inside JSON strings. Paths with colons must stay inside quoted strings.
Keep output compact: complete valid JSON in one response; close all braces and quotes.

Query: {query}

Chunks:
{chunks}
"""

_EXTRACT_PROMPT_COMPACT = """Extract a minimal knowledge graph. Return one complete JSON object only.
Keys: summary, entities (max 6), relations (max 4), claims (max 6).
Keep summary under 80 words; each claim text under 100 characters.

entities: {{"id","name","type"}}
relations: {{"source_id","target_id","type","weight"}}
claims: {{"id","text","entity_id","confidence","grandchild_id"}}

Query: {query}

Chunks:
{chunks}
"""

_EXTRACT_MAX_TOKENS = 2048
_CHUNK_TEXT_LIMIT = 800
_CHUNK_TEXT_LIMIT_COMPACT = 400


class LiquidExtractError(ValueError):
    """Raised when LLM output cannot be parsed into graph structure."""


def _strip_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    return cleaned.strip()


def _load_payload_dict(raw: str) -> tuple[dict[str, Any], str]:
    """Parse LLM output — JSON first (robust for colons in paths), YAML fallback."""
    stripped = _strip_fences(raw)
    if not stripped:
        raise LiquidExtractError("empty extraction output")

    try:
        payload = json.loads(stripped)
        if isinstance(payload, dict):
            return payload, "json"
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", stripped)
    if match:
        try:
            payload = json.loads(match.group())
            if isinstance(payload, dict):
                return payload, "json_brace_extract"
        except json.JSONDecodeError:
            pass

    try:
        payload = yaml.safe_load(stripped)
    except yaml.YAMLError as exc:
        raise LiquidExtractError(f"invalid extraction output: {exc}") from exc

    if not isinstance(payload, dict):
        raise LiquidExtractError("extraction root must be a mapping")
    return payload, "yaml"


def _graph_from_payload(payload: dict[str, Any]) -> GraphExtractResult:
    entities: list[ExtractEntity] = []
    for row in payload.get("entities") or []:
        if not isinstance(row, dict):
            continue
        eid = str(row.get("id") or row.get("entity_id") or "").strip()
        name = str(row.get("name") or "").strip()
        if not eid or not name:
            continue
        entities.append(
            ExtractEntity(
                entity_id=eid,
                name=name,
                type=str(row.get("type") or "concept"),
            )
        )

    relations: list[ExtractRelation] = []
    for row in payload.get("relations") or []:
        if not isinstance(row, dict):
            continue
        src = str(row.get("source_id") or row.get("source") or "").strip()
        tgt = str(row.get("target_id") or row.get("target") or "").strip()
        if not src or not tgt:
            continue
        relations.append(
            ExtractRelation(
                source_id=src,
                target_id=tgt,
                type=str(row.get("type") or "related_to"),
                weight=float(row.get("weight") or 1.0),
            )
        )

    claims: list[ExtractClaim] = []
    for row in payload.get("claims") or []:
        if not isinstance(row, dict):
            continue
        cid = str(row.get("id") or row.get("claim_id") or "").strip()
        text = str(row.get("text") or "").strip()
        if not cid or not text:
            continue
        claims.append(
            ExtractClaim(
                claim_id=cid,
                text=text,
                entity_id=(str(row["entity_id"]).strip() if row.get("entity_id") else None),
                confidence=float(row.get("confidence") or 0.5),
                grandchild_id=(
                    str(row["grandchild_id"]).strip() if row.get("grandchild_id") else None
                ),
            )
        )

    if not entities and not claims:
        raise LiquidExtractError("no entities or claims parsed")

    return GraphExtractResult(
        summary=str(payload.get("summary") or "").strip(),
        entities=entities,
        relations=relations,
        claims=claims,
    )


def parse_graph_yaml(raw: str) -> GraphExtractResult:
    """Parse schema-constrained JSON/YAML from Liquid output."""
    payload, _fmt = _load_payload_dict(raw)
    return _graph_from_payload(payload)


def _format_chunks(chunks: list[dict[str, Any]], *, text_limit: int = _CHUNK_TEXT_LIMIT) -> str:
    lines: list[str] = []
    for row in chunks:
        gid = row.get("id") or row.get("grandchild_id")
        score = row.get("fusion_score", row.get("score"))
        content = (row.get("content") or "")[:text_limit]
        lines.append(f"- grandchild_id: {gid}\n  score: {score}\n  text: {content}")
    return "\n".join(lines)


def build_extract_prompt(query_text: str, chunks: list[dict[str, Any]]) -> str:
    return _EXTRACT_PROMPT.format(
        query=query_text.strip(),
        chunks=_format_chunks(chunks, text_limit=_CHUNK_TEXT_LIMIT),
    )


def build_extract_prompt_compact(query_text: str, chunks: list[dict[str, Any]]) -> str:
    return _EXTRACT_PROMPT_COMPACT.format(
        query=query_text.strip(),
        chunks=_format_chunks(chunks, text_limit=_CHUNK_TEXT_LIMIT_COMPACT),
    )


def extract_graph_from_chunks(
    chunks: list[dict[str, Any]],
    query_text: str,
    *,
    llm: Any | None = None,
) -> GraphExtractResult:
    """Run Liquid extract when llm provided; otherwise requires pre-filled llm in tests."""
    if llm is None:
        raise LiquidExtractError("llm instance required for extraction")
    from app.services.extract_llm import run_extract_chat

    attempts: list[tuple[str, Any]] = [
        ("full", build_extract_prompt),
        ("compact", build_extract_prompt_compact),
    ]
    last_exc: LiquidExtractError | None = None

    for _attempt_name, prompt_builder in attempts:
        prompt = prompt_builder(query_text, chunks)
        raw = run_extract_chat(
            llm,
            [{"role": "user", "content": prompt}],
            max_new_tokens=_EXTRACT_MAX_TOKENS,
        )
        try:
            return parse_graph_yaml(raw)
        except LiquidExtractError as exc:
            last_exc = exc
            continue

    if last_exc is not None:
        raise last_exc
    raise LiquidExtractError("extraction failed after retries")
