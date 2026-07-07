"""Build-time model downloader — ensures Qwen GGUF is present; downloads if missing."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from huggingface_hub import hf_hub_download

REPO_ID = "jica98/qwen3.5-4B-super-coder"
FILENAME = "qwen3.5-4B-super-coder.Q4_0.gguf"
MIN_SIZE_BYTES = 2_000_000_000  # sanity check for Q4_0 ~2.5 GB

MODEL_PATH = Path(os.environ.get("MODEL_PATH", "/app/models"))


def ensure_model() -> Path:
    dest = expected_model_path()
    try:
        verify_model(dest)
        return dest
    except (FileNotFoundError, ValueError):
        return download_qwen_model(MODEL_PATH)


def expected_model_path(model_dir: Path | None = None) -> Path:
    base = model_dir if model_dir is not None else MODEL_PATH
    return base / FILENAME


def verify_model(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"model file not found: {path}")
    size = path.stat().st_size
    if size < MIN_SIZE_BYTES:
        raise ValueError(
            f"model file too small ({size} bytes, expected >= {MIN_SIZE_BYTES}): {path}"
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


def main() -> None:
    MODEL_PATH.mkdir(parents=True, exist_ok=True)
    dest = expected_model_path()
    try:
        verify_model(dest)
        print(f"Model already present at {dest}")
        return
    except (FileNotFoundError, ValueError):
        pass
    try:
        dest = download_qwen_model(MODEL_PATH)
    except Exception as exc:
        print(f"Model download failed: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"Downloaded model to {dest}")


if __name__ == "__main__":
    main()
