"""Build-time model downloader — ensures Qwen GGUF and Jina embeddings are present."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from huggingface_hub import hf_hub_download, snapshot_download

REPO_ID = "jica98/qwen3.5-4B-super-coder"
FILENAME = "qwen3.5-4B-super-coder.Q4_0.gguf"
MIN_SIZE_BYTES = 2_000_000_000  # sanity check for Q4_0 ~2.5 GB

JINA_REPO_ID = "jinaai/jina-embeddings-v5-omni-small"
JINA_SUBDIR = "jina-embeddings-v5-omni-small"

MODEL_PATH = Path(os.environ.get("MODEL_PATH", "/app/models"))


def expected_model_path(model_dir: Path | None = None) -> Path:
    base = model_dir if model_dir is not None else MODEL_PATH
    return base / FILENAME


def expected_jina_model_path(model_dir: Path | None = None) -> Path:
    base = model_dir if model_dir is not None else MODEL_PATH
    return base / JINA_SUBDIR


def verify_model(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"model file not found: {path}")
    size = path.stat().st_size
    if size < MIN_SIZE_BYTES:
        raise ValueError(
            f"model file too small ({size} bytes, expected >= {MIN_SIZE_BYTES}): {path}"
        )


def verify_jina_model(path: Path) -> None:
    config = path / "config.json"
    if not config.is_file():
        raise FileNotFoundError(f"Jina config not found: {config}")
    weights = path / "model.safetensors"
    pytorch_weights = path / "pytorch_model.bin"
    if not weights.is_file() and not pytorch_weights.is_file():
        raise FileNotFoundError(
            f"Jina weights not found in {path} (expected model.safetensors or pytorch_model.bin)"
        )


def download_qwen_model(model_dir: Path) -> Path:
    model_dir.mkdir(parents=True, exist_ok=True)
    hf_hub_download(
        repo_id=REPO_ID,
        filename=FILENAME,
        local_dir=str(model_dir),
        local_dir_use_symlinks=False,
    )
    dest = expected_model_path(model_dir)
    verify_model(dest)
    return dest


def download_jina_model(model_dir: Path) -> Path:
    dest = expected_jina_model_path(model_dir)
    dest.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=JINA_REPO_ID,
        local_dir=str(dest),
    )
    verify_jina_model(dest)
    return dest


def ensure_qwen_model() -> Path:
    dest = expected_model_path()
    try:
        verify_model(dest)
        return dest
    except (FileNotFoundError, ValueError):
        return download_qwen_model(MODEL_PATH)


def ensure_jina_model() -> Path:
    dest = expected_jina_model_path()
    try:
        verify_jina_model(dest)
        return dest
    except FileNotFoundError:
        return download_jina_model(MODEL_PATH)


def ensure_model() -> Path:
    qwen = ensure_qwen_model()
    ensure_jina_model()
    return qwen


def main() -> None:
    MODEL_PATH.mkdir(parents=True, exist_ok=True)
    try:
        qwen = ensure_qwen_model()
        print(f"Qwen model ready at {qwen}")
        jina = ensure_jina_model()
        print(f"Jina model ready at {jina}")
    except Exception as exc:
        print(f"Model ensure failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
