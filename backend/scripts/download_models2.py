import os
from huggingface_hub import snapshot_download

MODELS = [
    "jinaai/jina-embeddings-v5-text-small",
    "jinaai/jina-reranker-v3",
]

# 支援 optional 下載 BGE-M3
if os.environ.get("DOWNLOAD_BGE", "0") == "1":
    MODELS.extend(["BAAI/bge-m3", "BAAI/bge-reranker-base"])

target_root = "/app/models"
os.makedirs(target_root, exist_ok=True)

for repo_id in MODELS:
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