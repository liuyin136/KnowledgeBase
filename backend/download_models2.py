"""Build-time model downloader — Qwen, LiquidAI, and Jina GGUF models."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Literal

from huggingface_hub import hf_hub_download

REPO_ID = "jica98/qwen3.5-4B-super-coder"
FILENAME = "qwen3.5-4B-super-coder.Q4_0.gguf"
MIN_SIZE_BYTES = 2_000_000_000  # sanity check for Q4_0 ~2.5 GB

MODEL_PATH = Path(os.environ.get("MODEL_PATH", "/app/models"))

# ---------------------------------------------------------------------------
# LiquidAI GGUF registry
# ---------------------------------------------------------------------------
LIQUID_SUBDIR = "liquid"

LIQUID_MODELS: dict[str, dict[str, str | int]] = {
    "liquid-350m": {
        "repo_id": "LiquidAI/LFM2.5-350M-GGUF",
        "filename": "LFM2.5-350M-BF16.gguf",
        "min_bytes": 600_000_000,
    },
    "liquid-8b": {
        "repo_id": "LiquidAI/LFM2.5-8B-A1B-GGUF",
        "filename": "LFM2.5-8B-A1B-Q4_K_M.gguf",
        "min_bytes": 4_000_000_000,
    },
    "liquid-vl-extract": {
        "repo_id": "LiquidAI/LFM2.5-VL-1.6B-Extract-GGUF",
        "filename": "LFM2.5-VL-1.6B-Extract-F16.gguf",
        "min_bytes": 2_000_000_000,
    },
    "liquid-vl-mmproj": {
        "repo_id": "LiquidAI/LFM2.5-VL-1.6B-Extract-GGUF",
        "filename": "mmproj-LFM2.5-VL-1.6B-Extract-F16.gguf",
        "min_bytes": 800_000_000,
    },
    "liquid-thinking": {
        "repo_id": "LiquidAI/LFM2.5-1.2B-Thinking-GGUF",
        "filename": "LFM2.5-1.2B-Thinking-BF16.gguf",
        "min_bytes": 2_000_000_000,
    },
    "liquid-rag": {
        "repo_id": "LiquidAI/LFM2-1.2B-RAG-GGUF",
        "filename": "LFM2-1.2B-RAG-F16.gguf",
        "min_bytes": 2_000_000_000,
    },
    "liquid-instruct": {
        "repo_id": "LiquidAI/LFM2.5-1.2B-Instruct-GGUF",
        "filename": "LFM2.5-1.2B-Instruct-BF16.gguf",
        "min_bytes": 2_000_000_000,
    },
    "liquid-extract": {
        "repo_id": "LiquidAI/LFM2-1.2B-Extract-GGUF",
        "filename": "LFM2-1.2B-Extract-F16.gguf",
        "min_bytes": 2_000_000_000,
    },
}

LIQUID_MIN_BYTES: dict[str, int] = {
    key: int(meta["min_bytes"]) for key, meta in LIQUID_MODELS.items()
}

# ---------------------------------------------------------------------------
# Jina v5 omni GGUF — four tasks (text + vision-mmproj each)
# ---------------------------------------------------------------------------
JINA_SUBDIR = "jina"
JINA_TASKS = ("retrieval", "clustering", "classification", "text-matching")
JinaKind = Literal["text", "vision"]

JINA_TEXT_MIN_BYTES = 1_000_000_000
JINA_VISION_MIN_BYTES = 600_000_000
JINA_RERANKER_REPO_ID = "jinaai/jina-reranker-v3-GGUF"
JINA_RERANKER_FILENAME = "jina-reranker-v3-BF16.gguf"
JINA_RERANKER_PROJECTOR_FILENAME = "projector.safetensors"
JINA_RERANKER_MIN_BYTES = 1_000_000_000
JINA_RERANKER_PROJECTOR_MIN_BYTES = 1_000_000

def _jina_repo_id(task: str) -> str:
    return f"jinaai/jina-embeddings-v5-omni-small-{task}-GGUF"

def _jina_text_filename(task: str) -> str:
    return f"jina-embeddings-v5-omni-small-{task}-F16.gguf"

def _jina_vision_filename(task: str) -> str:
    return f"jina-embeddings-v5-omni-small-{task}-vision-mmproj-F16.gguf"

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------
def expected_model_path(model_dir: Path | None = None) -> Path:
    base = model_dir if model_dir is not None else MODEL_PATH
    return base / FILENAME


def expected_liquid_path(key: str, model_dir: Path | None = None) -> Path:
    if key not in LIQUID_MODELS:
        raise KeyError(f"unknown liquid model key: {key}")
    base = model_dir if model_dir is not None else MODEL_PATH
    return base / LIQUID_SUBDIR / str(LIQUID_MODELS[key]["filename"])


def expected_jina_gguf_path(
    task: str,
    kind: JinaKind = "text",
    model_dir: Path | None = None,
) -> Path:
    if task not in JINA_TASKS:
        raise KeyError(f"unknown jina task: {task}")
    base = model_dir if model_dir is not None else MODEL_PATH
    filename = _jina_text_filename(task) if kind == "text" else _jina_vision_filename(task)
    return base / JINA_SUBDIR / task / filename

def expected_jina_reranker_path(model_dir: Path | None = None) -> Path:
    base = model_dir if model_dir is not None else MODEL_PATH
    return base / JINA_SUBDIR / "reranker" / JINA_RERANKER_FILENAME


def expected_jina_reranker_projector_path(model_dir: Path | None = None) -> Path:
    base = model_dir if model_dir is not None else MODEL_PATH
    return base / JINA_SUBDIR / "reranker" / JINA_RERANKER_PROJECTOR_FILENAME

# ---------------------------------------------------------------------------
# Verify / download
# ---------------------------------------------------------------------------
def verify_gguf_file(path: Path, min_bytes: int) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"model file not found: {path}")
    size = path.stat().st_size
    if size < min_bytes:
        raise ValueError(
            f"model file too small ({size} bytes, expected >= {min_bytes}): {path}"
        )


def verify_model(path: Path) -> None:
    verify_gguf_file(path, MIN_SIZE_BYTES)


def download_gguf_file(repo_id: str, filename: str, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        local_dir=str(dest_dir),
        local_dir_use_symlinks=False,
    )
    return dest_dir / filename


def download_qwen_model(model_dir: Path) -> Path:
    dest = download_gguf_file(REPO_ID, FILENAME, model_dir)
    verify_model(dest)
    return dest


def download_liquid_model(key: str, model_dir: Path) -> Path:
    meta = LIQUID_MODELS[key]
    dest_dir = model_dir / LIQUID_SUBDIR
    dest = download_gguf_file(str(meta["repo_id"]), str(meta["filename"]), dest_dir)
    verify_gguf_file(dest, int(meta["min_bytes"]))
    return dest


def download_jina_gguf(task: str, kind: JinaKind, model_dir: Path) -> Path:
    dest_dir = model_dir / JINA_SUBDIR / task
    filename = _jina_text_filename(task) if kind == "text" else _jina_vision_filename(task)
    min_bytes = JINA_TEXT_MIN_BYTES if kind == "text" else JINA_VISION_MIN_BYTES
    dest = download_gguf_file(_jina_repo_id(task), filename, dest_dir)
    verify_gguf_file(dest, min_bytes)
    return dest

def download_jina_reranker(model_dir: Path) -> list[Path]:
    dest_dir = model_dir / JINA_SUBDIR / "reranker"
    gguf = download_gguf_file(
        JINA_RERANKER_REPO_ID, JINA_RERANKER_FILENAME, dest_dir
    )
    verify_gguf_file(gguf, JINA_RERANKER_MIN_BYTES)
    projector = download_gguf_file(
        JINA_RERANKER_REPO_ID, JINA_RERANKER_PROJECTOR_FILENAME, dest_dir
    )
    verify_gguf_file(projector, JINA_RERANKER_PROJECTOR_MIN_BYTES)
    return [gguf, projector]


# ---------------------------------------------------------------------------
# Ensure (verify-then-download-if-missing)
# ---------------------------------------------------------------------------
def ensure_qwen_model() -> Path:
    dest = expected_model_path()
    try:
        verify_model(dest)
        return dest
    except (FileNotFoundError, ValueError):
        return download_qwen_model(MODEL_PATH)


def ensure_liquid_models() -> list[Path]:
    paths: list[Path] = []
    for key, meta in LIQUID_MODELS.items():
        dest = expected_liquid_path(key)
        try:
            verify_gguf_file(dest, int(meta["min_bytes"]))
        except (FileNotFoundError, ValueError):
            dest = download_liquid_model(key, MODEL_PATH)
        paths.append(dest)
    return paths


def ensure_jina_gguf_models() -> list[Path]:
    paths: list[Path] = []
    for task in JINA_TASKS:
        for kind, min_bytes in (
            ("text", JINA_TEXT_MIN_BYTES),
            ("vision", JINA_VISION_MIN_BYTES),
        ):
            dest = expected_jina_gguf_path(task, kind)  # type: ignore[arg-type]
            try:
                verify_gguf_file(dest, min_bytes)
            except (FileNotFoundError, ValueError):
                dest = download_jina_gguf(task, kind, MODEL_PATH)  # type: ignore[arg-type]
            paths.append(dest)
    return paths

def ensure_jina_reranker() -> list[Path]:
    gguf = expected_jina_reranker_path()
    projector = expected_jina_reranker_projector_path()
    try:
        verify_gguf_file(gguf, JINA_RERANKER_MIN_BYTES)
        verify_gguf_file(projector, JINA_RERANKER_PROJECTOR_MIN_BYTES)
        return [gguf, projector]
    except (FileNotFoundError, ValueError):
        return download_jina_reranker(MODEL_PATH)


def ensure_jina_reranker_models() -> list[Path]:
    return ensure_jina_reranker()


def ensure_model() -> Path:
    qwen = ensure_qwen_model()
    ensure_liquid_models()
    ensure_jina_gguf_models()
    ensure_jina_reranker()
    return qwen


def main() -> None:
    MODEL_PATH.mkdir(parents=True, exist_ok=True)
    try:
        qwen = ensure_qwen_model()
        print(f"Qwen model ready at {qwen}")
        for path in ensure_liquid_models():
            print(f"LiquidAI model ready at {path}")
        for path in ensure_jina_gguf_models():
            print(f"Jina GGUF ready at {path}")
        for path in ensure_jina_reranker():
            print(f"Jina reranker asset ready at {path}")
    except Exception as exc:
        print(f"Model ensure failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
