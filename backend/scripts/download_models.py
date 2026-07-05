"""
scripts/download_models.py — One-time model download (v1.3 — Jina default + BGE-M3 toggle).

Downloads (v1.3 default):
  • jinaai/jina-embeddings-v5-text-small   (1536-dim native → Matryoshka-truncated to 1024 at encode time)
  • jinaai/jina-reranker-v3                (cross-encoder, 8192 max length)

Optional (env `DOWNLOAD_BGE=1`): also download the BGE-M3 alternative family so
the operator can toggle EMBEDDING_MODEL=bge-m3 / RERANKER_MODEL=bge-reranker-base
without re-downloading:
  • BAAI/bge-m3                            (1024-dim embedding — alternative)
  • BAAI/bge-reranker-base                 (cross-encoder, 512 max length — alternative)

Into `MODEL_PATH/<repo-suffix>` (e.g. /app/models/jina-embeddings-v5-text-small),
so `services/embedding.py` + `services/retrieval.py` can resolve them by name.

Usage:
  python scripts/download_models.py                    # Jina v5 + Jina reranker v3 (v1.3 default)
  DOWNLOAD_BGE=1 python scripts/download_models.py     # ALSO download BGE-M3 + BGE-reranker-base
  DOWNLOAD_RERANKER=0 python scripts/download_models.py   # skip the default reranker

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

    # v1.3 default family: Jina v5 small embedding + Jina reranker v3.
    models = [settings.jina_v5_repo]
    if os.environ.get("DOWNLOAD_RERANKER", "1") == "1" and settings.enable_reranker:
        models.append(settings.jina_reranker_repo)

    # Optional: also download the BGE-M3 alternative family so the operator can
    # toggle EMBEDDING_MODEL=bge-m3 / RERANKER_MODEL=bge-reranker-base without
    # having to re-download later. Controlled by the DOWNLOAD_BGE env var.
    if os.environ.get("DOWNLOAD_BGE", "0") == "1":
        models.append(settings.bge_m3_repo)
        if settings.enable_reranker:
            models.append(settings.bge_reranker_repo)

    for repo_id in models:
        local_name = repo_id.split("/")[-1]
        dest = os.path.join(target_root, local_name)
        print(f"[download] {repo_id} -> {dest}", flush=True)
        snapshot_download(
            repo_id=repo_id,
            local_dir=dest,
            # Skip *.msgpack / *.h5 optimizer states to save disk.
            ignore_patterns=["*.msgpack", "*.h5", "rust_model.onnx", "onnx/*"],
            resume_download=True,
        )
    print(f"[download] done ({len(models)} model(s))", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
