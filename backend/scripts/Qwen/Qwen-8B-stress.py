# Run: docker compose exec api-worker python /app/scripts/Qwen/Qwen-8B-stress.py
# Optional: --targets 512,1024 --json-out /data/Debug/qwen-8b-stress.jsonl
"""Stress-test Query-Guided Extraction input token limits for Qwen3-8B."""
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

from scripts.Qwen._qwen_common import load_qwen3_4bit

SAMPLE_QUERY = "What are the recent advancements in Graph RAG and hybrid search?"
INPUT_TOKEN_TARGETS = [128, 256, 512, 1024, 2048, 4096, 8192, 16367, 32678]
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


def _build_messages(query: str, context_body: str, *, use_response_format: bool) -> list[dict[str, str]]:
    schema_hint = ""
    if use_response_format:
        schema_hint = f"\n5. JSON schema (for reference):\n{json.dumps(_graph_schema(), indent=2)}"

    system_prompt = f"""You are a strict data extraction AI executing Query-Guided Extraction.

Target Query: [{query}]
Focus on information relevant to the query: [{query}]

CRITICAL INSTRUCTIONS:
1. ONLY extract entities and relationships that directly help answer or provide context to the Target Query.
2. IGNORE any information in the chunks that is irrelevant to the query.
3. For every entity/relationship, you must cite the Chunk ID.
4. Output ONLY valid JSON matching the schema.{schema_hint}"""

    user_prompt = f"""Search Results Context:
[Chunk 1]
{context_body}

Extract matching the JSON schema:"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _count_prompt_tokens(tokenizer: Any, messages: list[dict[str, str]]) -> int:
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    return len(tokenizer.encode(text))


def _context_for_target_tokens(
    tokenizer: Any,
    query: str,
    corpus: str,
    target_tokens: int,
    *,
    use_response_format: bool,
) -> tuple[str, int]:
    lo, hi = 0, len(corpus)
    best_text = ""
    best_count = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        body = corpus[:mid]
        count = _count_prompt_tokens(
            tokenizer, _build_messages(query, body, use_response_format=use_response_format)
        )
        if count <= target_tokens:
            best_text = body
            best_count = count
            lo = mid + 1
        else:
            hi = mid - 1
    if not best_text:
        best_text = corpus[: min(4000, len(corpus))]
        best_count = _count_prompt_tokens(
            tokenizer,
            _build_messages(query, best_text, use_response_format=use_response_format),
        )
    return best_text, best_count


def _strip_json_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
    return cleaned.strip()


def _generate(
    tokenizer: Any,
    model: Any,
    messages: list[dict[str, str]],
    *,
    max_new_tokens: int,
) -> tuple[str, int, int]:
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    inputs = tokenizer([text], return_tensors="pt").to(model.device)
    prompt_tokens = int(inputs.input_ids.shape[1])
    output_ids = model.generate(
        **inputs,
        max_new_tokens=max_new_tokens,
        temperature=0.1,
        top_p=0.1,
        do_sample=True,
    )
    new_tokens = output_ids[0][prompt_tokens:].tolist()
    completion_tokens = len(new_tokens)
    content = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
    return content, prompt_tokens, completion_tokens


def _run_single(
    tokenizer: Any,
    model: Any,
    *,
    target_tokens: int,
    query: str,
    corpus: str,
    max_output_tokens: int,
    use_response_format: bool,
) -> dict[str, Any]:
    context_body, prompt_tokens_est = _context_for_target_tokens(
        tokenizer,
        query,
        corpus,
        target_tokens,
        use_response_format=use_response_format,
    )
    messages = _build_messages(query, context_body, use_response_format=use_response_format)

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
        content, prompt_tokens, completion_tokens = _generate(
            tokenizer,
            model,
            messages,
            max_new_tokens=max_output_tokens,
        )
        elapsed = time.perf_counter() - started
        row["elapsed_sec"] = round(elapsed, 3)
        row["prompt_tokens"] = prompt_tokens
        row["completion_tokens"] = completion_tokens
        row["total_tokens"] = prompt_tokens + completion_tokens
        row["output_chars"] = len(content)
        if content.strip():
            json.loads(_strip_json_fences(content))
        row["ok"] = True
    except Exception as exc:
        row["elapsed_sec"] = round(time.perf_counter() - started, 3)
        row["error"] = f"{type(exc).__name__}: {exc}"
        row["traceback"] = traceback.format_exc(limit=3)
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description="Qwen3-8B query-guided extraction token stress test")
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

    print("Model: Qwen3-8B (4-bit)")
    print(f"Corpus size: {len(corpus)} chars from repo documents")
    print(f"Targets: {targets}")
    print(f"response_format: {use_rf}")
    print("-" * 72)

    tokenizer, model = load_qwen3_4bit()
    results: list[dict[str, Any]] = []
    first_error: int | None = None

    try:
        for target in targets:
            row = _run_single(
                tokenizer,
                model,
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
        del model
        del tokenizer

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
