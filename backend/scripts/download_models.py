"""
scripts/download_models.py — One-time BGE-M3 (+ optional reranker) download.

Downloads:
  • BAAI/bge-m3                         (1024-dim embedding — primary)
  • BAAI/bge-reranker-base              (cross-encoder — optional, on by default)

Into `MODEL_PATH/bge-m3` and `MODEL_PATH/bge-reranker-base` (subdir per repo),
so `services/embedding.py` can resolve them by name.

Usage:
  python scripts/download_models.py
  DOWNLOAD_RERANKER=0 python scripts/download_models.py    # skip reranker

Idempotent: re-running skips already-downloaded files (huggingface_hub handles this).
"""

from __future__ import annotations

import os
import sys

# Allow running as a script (no package import).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings  # noqa: E402


def main() -> int:
    from huggingface_hub import snapshot_download

    target_root = settings.model_path
    os.makedirs(target_root, exist_ok=True)

    models = [settings.bge_m3_repo]
    if os.environ.get("DOWNLOAD_RERANKER", "1") == "1" and settings.enable_reranker:
        models.append(settings.bge_reranker_repo)

    for repo_id in models:
        local_name = repo_id.split("/")[-1]
        dest = os.path.join(target_root, local_name)
        print(f"[download] {repo_id} -> {dest}", flush=True)
        snapshot_download(
            repo_id=repo_id,
            local_dir=dest,
            # Skip *.msgpack / *.h5 optimizer states to save ~1GB off bge-m3.
            ignore_patterns=["*.msgpack", "*.h5", "rust_model.onnx", "onnx/*"],
            resume_download=True,
        )
    print("[download] done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
