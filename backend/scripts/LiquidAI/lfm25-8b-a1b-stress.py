# Run: docker compose exec api-worker python /app/scripts/LiquidAI/lfm25-8b-a1b-stress.py
# Optional: --targets 512,1024 --json-out /data/Debug/liquid-8b-stress.jsonl
"""Stress-test Query-Guided Extraction input token limits for liquid-8b."""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
import traceback
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.LiquidAI._liquid_common import load_liquid

MODEL_KEY_DEFAULT = "liquid-8b"
SAMPLE_QUERY = "What are the recent advancements in Graph RAG and hybrid search?"
INPUT_TOKEN_TARGETS = [31000]
CORPUS_SUFFIXES = {".md", ".py", ".txt", ".cypher"}
CORPUS_SKIP_DIRS = {
    ".git",
    ".cursor",
    "__pycache__",
    "node_modules",
    ".next",
    "models",
    "pic",
    "Debug",
}
MAX_CORPUS_FILES = 200


def _repo_roots() -> list[Path]:
    script = Path(__file__).resolve()
    candidates = [
        script.parents[3],  # KnowledgeBase3 when full tree present
        Path("/app"),
    ]
    roots: list[Path] = []
    for root in candidates:
        if root.exists() and root not in roots:
            roots.append(root)
    return roots


def _collect_corpus() -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for root in _repo_roots():
        files: list[Path] = []
        for suffix in CORPUS_SUFFIXES:
            files.extend(root.rglob(f"*{suffix}"))
        random.shuffle(files)
        for path in files[:MAX_CORPUS_FILES]:
            if any(skip in path.parts for skip in CORPUS_SKIP_DIRS):
                continue
            key = str(path)
            if key in seen:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore").strip()
            except OSError:
                continue
            if len(text) < 80:
                continue
            seen.add(key)
            parts.append(f"--- {path.name} ---\n{text}")
    if not parts:
        raise RuntimeError("no corpus text found under repo roots")
    return "\n\n".join(parts)


def _graph_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "type": {"type": "string"},
                        "description": {"type": "string"},
                        "source_chunks": {"type": "array", "items": {"type": "integer"}},
                    },
                    "required": ["name", "type", "description", "source_chunks"],
                },
            },
            "relationships": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string"},
                        "target": {"type": "string"},
                        "relation": {"type": "string"},
                        "evidence": {"type": "string"},
                        "source_chunk": {"type": "integer"},
                    },
                    "required": ["source", "target", "relation", "evidence", "source_chunk"],
                },
            },
        },
        "required": ["entities", "relationships"],
    }


def _build_messages(query: str, context_body: str) -> list[dict[str, str]]:
    system_prompt = f"""You are a strict data extraction AI executing Query-Guided Extraction.

Target Query: [{query}]
Focus on information relevant to the query: [{query}]

CRITICAL INSTRUCTIONS:
1. ONLY extract entities and relationships that directly help answer or provide context to the Target Query.
2. IGNORE any information in the chunks that is irrelevant to the query.
3. For every entity/relationship, you must cite the Chunk ID.
4. Output ONLY valid JSON matching the schema."""

    user_prompt = f"""Search Results Context:
[Chunk 1]
{context_body}

Extract matching the JSON schema:"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _count_prompt_tokens(llm: Any, messages: list[dict[str, str]]) -> int:
    try:
        prompt = llm.create_chat_completion(messages=messages, max_tokens=1, stream=False)
        usage = prompt.get("usage") or {}
        if usage.get("prompt_tokens") is not None:
            return int(usage["prompt_tokens"])
    except Exception:
        pass
    joined = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
    return len(llm.tokenize(joined.encode("utf-8")))


def _context_for_target_tokens(
    llm: Any,
    query: str,
    corpus: str,
    target_tokens: int,
) -> tuple[str, int]:
    lo, hi = 0, len(corpus)
    best_text = ""
    best_count = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        body = corpus[:mid]
        count = _count_prompt_tokens(llm, _build_messages(query, body))
        if count <= target_tokens:
            best_text = body
            best_count = count
            lo = mid + 1
        else:
            hi = mid - 1
    if not best_text:
        best_text = corpus[: min(4000, len(corpus))]
        best_count = _count_prompt_tokens(llm, _build_messages(query, best_text))
    return best_text, best_count


def _run_single(
    llm: Any,
    *,
    target_tokens: int,
    query: str,
    corpus: str,
    max_output_tokens: int,
    use_response_format: bool,
) -> dict[str, Any]:
    context_body, prompt_tokens_est = _context_for_target_tokens(llm, query, corpus, target_tokens)
    messages = _build_messages(query, context_body)
    kwargs: dict[str, Any] = {
        "max_tokens": max_output_tokens,
        "temperature": 0.1,
        "top_p": 0.1,
        "top_k": 50,
        "repeat_penalty": 1.05,
    }
    if use_response_format:
        kwargs["response_format"] = {"type": "json_object", "schema": _graph_schema()}

    started = time.perf_counter()
    row: dict[str, Any] = {
        "target_input_tokens": target_tokens,
        "prompt_tokens_est": prompt_tokens_est,
        "context_chars": len(context_body),
        "ok": False,
        "error": None,
        "elapsed_sec": None,
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
        "output_chars": None,
    }
    try:
        response = llm.create_chat_completion(messages=messages, **kwargs)
        elapsed = time.perf_counter() - started
        usage = response.get("usage") or {}
        content = response["choices"][0]["message"]["content"] or ""
        row["elapsed_sec"] = round(elapsed, 3)
        row["prompt_tokens"] = usage.get("prompt_tokens")
        row["completion_tokens"] = usage.get("completion_tokens")
        row["total_tokens"] = usage.get("total_tokens")
        row["output_chars"] = len(content)
        if content.strip():
            json.loads(_strip_json_fences(content))
        row["ok"] = True
    except Exception as exc:
        row["elapsed_sec"] = round(time.perf_counter() - started, 3)
        row["error"] = f"{type(exc).__name__}: {exc}"
        row["traceback"] = traceback.format_exc(limit=3)
    return row


def _strip_json_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
    return cleaned.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="liquid-8b query-guided extraction token stress test")
    parser.add_argument("--model", default=MODEL_KEY_DEFAULT, help="liquid model key from download_models2")
    parser.add_argument(
        "--targets",
        default=",".join(str(t) for t in INPUT_TOKEN_TARGETS),
        help="comma-separated target prompt token sizes",
    )
    parser.add_argument("--max-output-tokens", type=int, default=2048)
    parser.add_argument("--no-response-format", action="store_true")
    parser.add_argument("--json-out", default="", help="optional JSONL output path")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    targets = [int(x.strip()) for x in args.targets.split(",") if x.strip()]
    corpus = _collect_corpus()
    use_rf = not args.no_response_format

    print(f"Model: {args.model}")
    print(f"Corpus size: {len(corpus)} chars from repo documents")
    print(f"Targets: {targets}")
    print(f"response_format: {use_rf}")
    print("-" * 72)

    llm = load_liquid(args.model)
    results: list[dict[str, Any]] = []
    first_error: int | None = None

    try:
        for target in targets:
            row = _run_single(
                llm,
                target_tokens=target,
                query=SAMPLE_QUERY,
                corpus=corpus,
                max_output_tokens=args.max_output_tokens,
                use_response_format=use_rf,
            )
            results.append(row)
            if not row["ok"] and first_error is None:
                first_error = target
            status = "OK" if row["ok"] else f"ERR {row['error']}"
            print(
                f"target={target:>5}  est_in={row['prompt_tokens_est']:>5}  "
                f"in={row.get('prompt_tokens') or '-':>5}  "
                f"out={row.get('completion_tokens') or '-':>5}  "
                f"sec={row['elapsed_sec']:.3f}  {status}"
            )
    finally:
        del llm

    print("-" * 72)
    if first_error is not None:
        print(f"First error at target_input_tokens={first_error}")
    else:
        print("All targets completed without error")

    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as fh:
            for row in results:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
