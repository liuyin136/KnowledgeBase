"""Shared helpers for Jina v5 omni GGUF smoke-test scripts."""
from __future__ import annotations

import atexit
import base64
import io
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import llama_cpp
import numpy as np
from llama_cpp import Llama
from pdf2image import convert_from_path
from PIL import Image
from safetensors import safe_open

from download_models2 import (
    JINA_RERANKER_MIN_BYTES,
    JINA_RERANKER_PROJECTOR_MIN_BYTES,
    JINA_TEXT_MIN_BYTES,
    JINA_VISION_MIN_BYTES,
    expected_jina_gguf_path,
    expected_jina_reranker_path,
    expected_jina_reranker_projector_path,
    verify_gguf_file,
)

DATA_ROOT = Path("/data")
PIC_DIR = DATA_ROOT / "pic"
PDF_DIR = DATA_ROOT / "pdf"

_LLAMA_SERVER = "llama-server"
_LLAMA_EMBEDDING = "/usr/local/bin/llama-embedding"
_SERVER_HOST = "127.0.0.1"
_SERVER_BASE_PORT = 18080
_RERANK_DOC_EMBED_TOKEN = "<|embed_token|>"
_RERANK_QUERY_EMBED_TOKEN = "<|rerank_token|>"
_RERANK_DOC_EMBED_TOKEN_ID = 151670
_RERANK_QUERY_EMBED_TOKEN_ID = 151671
_CHAT_IM_END = "<|" + "im_end" + "|>"
_active_servers: dict[str, subprocess.Popen[bytes]] = {}
_server_markers: dict[str, str] = {}
_RERANK_N_CTX = int(os.environ.get("RERANK_N_CTX", "32768"))
_RERANK_N_BATCH = int(os.environ.get("RERANK_N_BATCH", "32768"))
_tokenize_llm: Llama | None = None
_tokenize_model_path: Path | None = None


def require_assets(paths: list[Path]) -> None:
    missing = [p for p in paths if not p.is_file()]
    if missing:
        print("Missing fixture files:", file=sys.stderr)
        for p in missing:
            print(f"  - {p}", file=sys.stderr)
        sys.exit(1)


def to_float32_numpy(vec) -> np.ndarray:
    """F16/BF16 GGUF outputs are not numpy-safe; always cast via float32."""
    arr = np.asarray(vec, dtype=np.float32)
    # llama-server may return [[dim]] nested lists
    while arr.ndim > 1 and arr.shape[0] == 1:
        arr = arr[0]
    arr = arr.reshape(-1)
    norm = float(np.linalg.norm(arr))
    return arr / norm if norm > 0 else arr


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def load_jina_text(task: str) -> Llama:
    path = expected_jina_gguf_path(task, "text")
    try:
        verify_gguf_file(path, JINA_TEXT_MIN_BYTES)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Jina text GGUF not available: {exc}", file=sys.stderr)
        sys.exit(1)

    return Llama(
        model_path=str(path),
        embedding=True,
        pooling_type=llama_cpp.LLAMA_POOLING_TYPE_LAST,
        n_gpu_layers=-1,
        n_ctx=32768,
        verbose=False,
        flash_attn=1
    )


def embed_text(llm: Llama, text: str) -> np.ndarray:
    out = llm.embed(text)
    if isinstance(out, list) and out and isinstance(out[0], (list, np.ndarray)):
        out = out[0]
    return to_float32_numpy(out)


def _task_port(task: str) -> int:
    return _SERVER_BASE_PORT + abs(hash(task)) % 1000


def _stop_server(task: str) -> None:
    proc = _active_servers.pop(task, None)
    _server_markers.pop(task, None)
    if proc is None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def _image_to_png_b64(image_path: Path) -> str:
    """Decode via PIL and re-encode as PNG — JPEG bytes fail mtmd decode on this fork."""
    with Image.open(image_path) as img:
        rgb = img.convert("RGB")
        buf = io.BytesIO()
        rgb.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _ensure_server(task: str) -> tuple[str, str]:
    """Return (base_url, media_marker) for a healthy llama-server."""
    if (
        task in _active_servers
        and _active_servers[task].poll() is None
        and task in _server_markers
    ):
        return f"http://{_SERVER_HOST}:{_task_port(task)}", _server_markers[task]

    text_path = expected_jina_gguf_path(task, "text")
    vision_path = expected_jina_gguf_path(task, "vision")
    try:
        verify_gguf_file(text_path, JINA_TEXT_MIN_BYTES)
        verify_gguf_file(vision_path, JINA_VISION_MIN_BYTES)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Jina GGUF not available for server: {exc}", file=sys.stderr)
        sys.exit(1)

    port = _task_port(task)
    base_url = f"http://{_SERVER_HOST}:{port}"
    cmd = [
        _LLAMA_SERVER,
        "-m",
        str(text_path),
        "--mmproj",
        str(vision_path),
        "--embedding",
        "--pooling",
        "last",
        "--host",
        _SERVER_HOST,
        "--port",
        str(port),
        "-ngl",
        "99",
        "-c",
        "8192",
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    _active_servers[task] = proc
    atexit.register(_stop_server, task)

    deadline = time.time() + 120
    while time.time() < deadline:
        if proc.poll() is not None:
            err = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
            print(f"llama-server exited early for task={task}:\n{err}", file=sys.stderr)
            sys.exit(1)
        try:
            r = httpx.get(f"{base_url}/health", timeout=2.0)
            if r.status_code == 200:
                props = httpx.get(f"{base_url}/props", timeout=5.0)
                props.raise_for_status()
                marker = props.json().get("media_marker")
                if not marker:
                    print(
                        f"llama-server /props missing media_marker for task={task}",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                _server_markers[task] = marker
                return base_url, marker
        except httpx.HTTPError:
            pass
        time.sleep(1.0)

    _stop_server(task)
    print(f"llama-server failed to become healthy for task={task}", file=sys.stderr)
    sys.exit(1)


def _embed_via_server(task: str, multimodal_b64: list[str]) -> np.ndarray:
    base_url, marker = _ensure_server(task)
    payload = {
        "content": [
            {
                "prompt_string": marker,
                "multimodal_data": multimodal_b64,
            }
        ]
    }
    with httpx.Client(timeout=180.0) as client:
        resp = client.post(f"{base_url}/embeddings", json=payload)
        resp.raise_for_status()
        data = resp.json()

    if isinstance(data, list):
        emb = data[0]["embedding"]
    elif isinstance(data, dict) and "data" in data:
        emb = data["data"][0]["embedding"]
    else:
        emb = data[0]["embedding"]
    return to_float32_numpy(emb)


def embed_image(task: str, image_path: Path) -> np.ndarray:
    return _embed_via_server(task, [_image_to_png_b64(image_path)])


def embed_pdf_page(task: str, pdf_path: Path) -> np.ndarray:
    pages = convert_from_path(str(pdf_path), first_page=1, last_page=1)
    tmp = pdf_path.with_suffix(".page1.png")
    try:
        pages[0].save(tmp, format="PNG")
        return embed_image(task, tmp)
    finally:
        if tmp.is_file():
            tmp.unlink()


@dataclass(frozen=True)
class JinaRerankResult:
    index: int
    relevance_score: float
    document: str


class JinaReranker:
    """GGUF jina-reranker-v3 using llama.cpp per-token embeddings + projector (HF-compatible)."""

    def __init__(
        self,
        model_path: Path,
        projector_path: Path,
        llama_embedding: str = _LLAMA_EMBEDDING,
        *,
        n_ctx: int | None = None,
        n_batch: int | None = None,
    ) -> None:
        self.model_path = model_path
        self.projector_path = projector_path
        self.llama_embedding = llama_embedding
        self.n_ctx = n_ctx if n_ctx is not None else _RERANK_N_CTX
        self.n_batch = n_batch if n_batch is not None else _RERANK_N_BATCH
        self._projector = _load_reranker_projector(projector_path)
        self._embed_llm: Llama | None = None

    def rerank(
        self,
        query: str,
        documents: list[str],
        *,
        top_n: int | None = None,
        instruction: str | None = None,
    ) -> list[JinaRerankResult]:
        if not documents:
            return []

        prompt = _format_rerank_prompt(query, documents, instruction=instruction)
        llm = self._ensure_embed_llm()
        embeddings = _rerank_hidden_states(prompt, llm)

        doc_positions = _marker_token_ends(llm, prompt, _RERANK_DOC_EMBED_TOKEN)
        query_positions = _marker_token_ends(llm, prompt, _RERANK_QUERY_EMBED_TOKEN, last=True)
        if len(query_positions) == 0:
            raise ValueError(f"query embed token {_RERANK_QUERY_EMBED_TOKEN!r} not found in prompt")
        if len(doc_positions) == 0:
            raise ValueError(f"document embed tokens {_RERANK_DOC_EMBED_TOKEN!r} not found in prompt")
        if len(doc_positions) != len(documents):
            raise ValueError(
                f"expected {len(documents)} document embed markers, found {len(doc_positions)}"
            )

        query_pos = query_positions[0]
        if query_pos >= len(embeddings):
            raise ValueError(
                f"query embed position {query_pos} out of range for {len(embeddings)} embeddings"
            )
        for pos in doc_positions:
            if pos >= len(embeddings):
                raise ValueError(
                    f"document embed position {pos} out of range for {len(embeddings)} embeddings"
                )

        query_hidden = embeddings[query_pos : query_pos + 1]
        doc_hidden = embeddings[doc_positions]
        query_embeds = _apply_reranker_projector(self._projector, query_hidden)
        doc_embeds = _apply_reranker_projector(self._projector, doc_hidden)
        scores = _cosine_scores(doc_embeds, query_embeds)

        results = [
            JinaRerankResult(index=idx, relevance_score=float(score), document=doc)
            for idx, (doc, score) in enumerate(zip(documents, scores, strict=True))
        ]
        results.sort(key=lambda item: item.relevance_score, reverse=True)
        if top_n is not None:
            return results[:top_n]
        return results

    def _ensure_embed_llm(self) -> Llama:
        if self._embed_llm is None:
            self._embed_llm = Llama(
                model_path=str(self.model_path),
                embedding=True,
                pooling_type=llama_cpp.LLAMA_POOLING_TYPE_NONE,
                n_gpu_layers=-1,
                n_ctx=self.n_ctx,
                n_batch=self.n_batch,
                verbose=False,
            )
        return self._embed_llm


def _get_rerank_tokenize_llm(model_path: Path) -> Llama:
    global _tokenize_llm, _tokenize_model_path
    if _tokenize_llm is None or _tokenize_model_path != model_path:
        if _tokenize_llm is not None:
            close = getattr(_tokenize_llm, "close", None)
            if callable(close):
                close()
            _tokenize_llm = None
        _tokenize_llm = Llama(
            model_path=str(model_path),
            embedding=True,
            pooling_type=llama_cpp.LLAMA_POOLING_TYPE_NONE,
            n_gpu_layers=-1,
            n_ctx=512,
            n_batch=512,
            verbose=False,
        )
        _tokenize_model_path = model_path
    return _tokenize_llm


def estimate_rerank_prompt_tokens(
    query: str,
    documents: list[str],
    *,
    instruction: str | None = None,
    model_path: Path | None = None,
) -> int:
    path = model_path or expected_jina_reranker_path()
    verify_gguf_file(path, JINA_RERANKER_MIN_BYTES)
    llm = _get_rerank_tokenize_llm(path)
    prompt = _format_rerank_prompt(query, documents, instruction=instruction)
    return len(llm.tokenize(prompt.encode("utf-8")))


def _load_reranker_projector(projector_path: Path) -> tuple[np.ndarray, np.ndarray]:
    with safe_open(str(projector_path), framework="numpy") as tensors:
        linear1 = tensors.get_tensor("projector.0.weight")
        linear2 = tensors.get_tensor("projector.2.weight")
    return linear1, linear2


def _apply_reranker_projector(
    projector: tuple[np.ndarray, np.ndarray],
    hidden: np.ndarray,
) -> np.ndarray:
    linear1, linear2 = projector
    x = hidden @ linear1.T
    x = np.maximum(0, x)
    return x @ linear2.T


def _sanitize_rerank_text(text: str) -> str:
    for token in (_RERANK_DOC_EMBED_TOKEN, _RERANK_QUERY_EMBED_TOKEN):
        text = text.replace(token, "")
    return text


def _format_rerank_prompt(
    query: str,
    documents: list[str],
    *,
    instruction: str | None = None,
) -> str:
    query = _sanitize_rerank_text(query)
    documents = [_sanitize_rerank_text(doc) for doc in documents]

    prefix = (
        "<|im_start|>system\n"
        "You are a search relevance expert who can determine a ranking of the passages "
        "based on how relevant they are to the query. "
        "If the query is a question, how relevant a passage is depends on how well it "
        "answers the question. "
        "If not, try to analyze the intent of the query and assess how well each passage "
        "satisfies the intent. "
        "If an instruction is provided, you should follow the instruction when determining "
        "the ranking."
        f"{_CHAT_IM_END}\n<|im_start|>user\n"
    )
    suffix = f"{_CHAT_IM_END}\n<|im_start|>assistant\n"

    prompt = (
        f"I will provide you with {len(documents)} passages, each indicated by a numerical "
        f"identifier. Rank the passages based on their relevance to query: {query}\n"
    )
    if instruction:
        prompt += f" \n{instruction}\n \n"

    doc_prompts = [
        f" \n{doc}{_RERANK_DOC_EMBED_TOKEN}\n " for doc in documents
    ]
    prompt += "\n".join(doc_prompts) + "\n"
    prompt += f" \n{query}{_RERANK_QUERY_EMBED_TOKEN}\n "
    return prefix + prompt + suffix


def _marker_token_ends(
    llm: Llama,
    prompt: str,
    marker: str,
    *,
    last: bool = False,
) -> list[int]:
    positions: list[int] = []
    start = 0
    while True:
        idx = prompt.find(marker, start)
        if idx < 0:
            break
        end = idx + len(marker)
        positions.append(len(llm.tokenize(prompt[:end].encode("utf-8"))) - 1)
        if last:
            break
        start = end
    if last and positions:
        return [positions[-1]]
    return positions


def _rerank_hidden_states(prompt: str, embed_llm: Llama) -> np.ndarray:
    raw = embed_llm.embed(prompt)
    rows: list[np.ndarray] = []
    for item in raw:
        vec = item
        if isinstance(vec, list) and vec and isinstance(vec[0], (list, np.ndarray)):
            vec = vec[0]
        arr = np.asarray(vec, dtype=np.float32).reshape(-1)
        rows.append(arr)
    return np.asarray(rows, dtype=np.float32)


def _cosine_scores(doc_embeds: np.ndarray, query_embeds: np.ndarray) -> np.ndarray:
    query = np.tile(query_embeds, (len(doc_embeds), 1))
    dot = np.sum(doc_embeds * query, axis=-1)
    doc_norm = np.sqrt(np.sum(doc_embeds * doc_embeds, axis=-1))
    query_norm = np.sqrt(np.sum(query * query, axis=-1))
    return dot / (doc_norm * query_norm)


def load_jina_reranker(
    *,
    n_ctx: int | None = None,
    n_batch: int | None = None,
) -> JinaReranker:
    model_path = expected_jina_reranker_path()
    projector_path = expected_jina_reranker_projector_path()
    try:
        verify_gguf_file(model_path, JINA_RERANKER_MIN_BYTES)
        verify_gguf_file(projector_path, JINA_RERANKER_PROJECTOR_MIN_BYTES)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Jina reranker assets not available: {exc}", file=sys.stderr)
        sys.exit(1)

    return JinaReranker(
        model_path=model_path,
        projector_path=projector_path,
        n_ctx=n_ctx,
        n_batch=n_batch,
    )


def rerank_documents(
    query: str,
    documents: list[str],
    *,
    top_n: int | None = None,
    instruction: str | None = None,
    reranker: JinaReranker | None = None,
) -> list[JinaRerankResult]:
    model = reranker or load_jina_reranker()
    return model.rerank(query, documents, top_n=top_n, instruction=instruction)
