from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings


def main() -> int:
    from huggingface_hub import snapshot_download

    target_root = settings.model_path
    os.makedirs(target_root, exist_ok=True)

    # 優先使用新的 embedding_repo（預設 Jina v5）
    models = [settings.embedding_repo]

    # 如果想強制下載 BGE-M3，可以用 DOWNLOAD_BGE=1
    if os.environ.get("DOWNLOAD_BGE", "0") == "1":
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
            local_dir_use_symlinks=False,
            ignore_patterns=["*.msgpack", "*.h5", "rust_model.onnx", "onnx/*"],
            resume_download=True,
        )

    print("[download] done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())