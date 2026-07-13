"""Build-time model downloader — LiquidAI, Jina retrieval+reranker, GLiNER2, Qwen3-8B."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from huggingface_hub import hf_hub_download

MODEL_PATH = Path(os.environ.get("MODEL_PATH", "/app/models"))

# ---------------------------------------------------------------------------
# LiquidAI GGUF registry (blueprint/stress scripts only)
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
}

LIQUID_MIN_BYTES: dict[str, int] = {
    key: int(meta["min_bytes"]) for key, meta in LIQUID_MODELS.items()
}

# ---------------------------------------------------------------------------
# GLiNER2 + Qwen3-8B (library from_pretrained at build, 4-bit bitsandbytes at runtime)
# ---------------------------------------------------------------------------
GLINER2_SUBDIR = "GLiNER2"
GLINER2_REPO = "fastino/gliner2-base-v1"

QWEN3_SUBDIR = "Qwen3-8B"
QWEN3_REPO = "Qwen/Qwen3-8B"

# ---------------------------------------------------------------------------
# Jina — retrieval text GGUF + reranker only (no vision / other tasks)
# ---------------------------------------------------------------------------
JINA_SUBDIR = "jina"
JINA_RETRIEVAL_TASK = "retrieval"

JINA_TEXT_MIN_BYTES = 1_000_000_000
JINA_RERANKER_REPO_ID = "jinaai/jina-reranker-v3-GGUF"
JINA_RERANKER_FILENAME = "jina-reranker-v3-BF16.gguf"
JINA_RERANKER_PROJECTOR_FILENAME = "projector.safetensors"
JINA_RERANKER_MIN_BYTES = 1_000_000_000
JINA_RERANKER_PROJECTOR_MIN_BYTES = 1_000_000


def _jina_retrieval_repo_id() -> str:
    return f"jinaai/jina-embeddings-v5-omni-small-{JINA_RETRIEVAL_TASK}-GGUF"


def _jina_retrieval_filename() -> str:
    return f"jina-embeddings-v5-omni-small-{JINA_RETRIEVAL_TASK}-F16.gguf"


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------
def expected_liquid_path(key: str, model_dir: Path | None = None) -> Path:
    if key not in LIQUID_MODELS:
        raise KeyError(f"unknown liquid model key: {key}")
    base = model_dir if model_dir is not None else MODEL_PATH
    return base / LIQUID_SUBDIR / str(LIQUID_MODELS[key]["filename"])


def expected_gliner2_path(model_dir: Path | None = None) -> Path:
    base = model_dir if model_dir is not None else MODEL_PATH
    return base / GLINER2_SUBDIR


def expected_qwen3_path(model_dir: Path | None = None) -> Path:
    base = model_dir if model_dir is not None else MODEL_PATH
    return base / QWEN3_SUBDIR


def expected_jina_retrieval_path(model_dir: Path | None = None) -> Path:
    base = model_dir if model_dir is not None else MODEL_PATH
    return base / JINA_SUBDIR / JINA_RETRIEVAL_TASK / _jina_retrieval_filename()


def expected_jina_gguf_path(task: str, kind: str = "text", model_dir: Path | None = None) -> Path:
    """Backward-compatible alias — production uses retrieval text only."""
    if task != JINA_RETRIEVAL_TASK or kind != "text":
        raise KeyError(f"only jina retrieval text is supported, got task={task!r} kind={kind!r}")
    return expected_jina_retrieval_path(model_dir)


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


def verify_pretrained_model_dir(path: Path, *, require_tokenizer: bool = False) -> None:
    config = path / "config.json"
    if not config.is_file():
        raise FileNotFoundError(f"pretrained config.json not found: {config}")
    if require_tokenizer:
        has_tokenizer = any(
            (path / name).is_file()
            for name in ("tokenizer.json", "tokenizer_config.json", "tokenizer.model")
        )
        if not has_tokenizer:
            raise FileNotFoundError(f"tokenizer files not found under: {path}")


verify_snapshot_model = verify_pretrained_model_dir


def download_gguf_file(repo_id: str, filename: str, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        local_dir=str(dest_dir),
        local_dir_use_symlinks=False,
    )
    return dest_dir / filename


def download_liquid_model(key: str, model_dir: Path) -> Path:
    meta = LIQUID_MODELS[key]
    dest_dir = model_dir / LIQUID_SUBDIR
    dest = download_gguf_file(str(meta["repo_id"]), str(meta["filename"]), dest_dir)
    verify_gguf_file(dest, int(meta["min_bytes"]))
    return dest


def download_gliner2_model(model_dir: Path) -> Path:
    from gliner2 import GLiNER2

    dest = model_dir / GLINER2_SUBDIR
    dest.mkdir(parents=True, exist_ok=True)
    extractor = GLiNER2.from_pretrained(GLINER2_REPO)
    extractor.save_pretrained(str(dest))
    verify_pretrained_model_dir(dest)
    return dest


def download_qwen3_model(model_dir: Path) -> Path:
    from transformers import AutoModelForCausalLM, AutoTokenizer

    dest = model_dir / QWEN3_SUBDIR
    dest.mkdir(parents=True, exist_ok=True)
    tokenizer = AutoTokenizer.from_pretrained(QWEN3_REPO)
    model = AutoModelForCausalLM.from_pretrained(QWEN3_REPO, low_cpu_mem_usage=True)
    tokenizer.save_pretrained(dest)
    model.save_pretrained(dest)
    verify_pretrained_model_dir(dest, require_tokenizer=True)
    return dest


def download_jina_retrieval_gguf(model_dir: Path) -> Path:
    dest_dir = model_dir / JINA_SUBDIR / JINA_RETRIEVAL_TASK
    dest = download_gguf_file(_jina_retrieval_repo_id(), _jina_retrieval_filename(), dest_dir)
    verify_gguf_file(dest, JINA_TEXT_MIN_BYTES)
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
# Ensure helpers (verify-then-download-if-missing)
# ---------------------------------------------------------------------------
def _ensure_liquid_models() -> list[Path]:
    paths: list[Path] = []
    for key, meta in LIQUID_MODELS.items():
        dest = expected_liquid_path(key)
        try:
            verify_gguf_file(dest, int(meta["min_bytes"]))
        except (FileNotFoundError, ValueError):
            dest = download_liquid_model(key, MODEL_PATH)
        paths.append(dest)
    return paths


def _ensure_gliner2_model() -> Path:
    dest = expected_gliner2_path()
    try:
        verify_pretrained_model_dir(dest)
        return dest
    except FileNotFoundError:
        return download_gliner2_model(MODEL_PATH)


def _ensure_qwen3_model() -> Path:
    dest = expected_qwen3_path()
    try:
        verify_pretrained_model_dir(dest, require_tokenizer=True)
        return dest
    except FileNotFoundError:
        return download_qwen3_model(MODEL_PATH)


def _ensure_jina_retrieval_gguf() -> Path:
    dest = expected_jina_retrieval_path()
    try:
        verify_gguf_file(dest, JINA_TEXT_MIN_BYTES)
        return dest
    except (FileNotFoundError, ValueError):
        return download_jina_retrieval_gguf(MODEL_PATH)


def _ensure_jina_reranker() -> list[Path]:
    gguf = expected_jina_reranker_path()
    projector = expected_jina_reranker_projector_path()
    try:
        verify_gguf_file(gguf, JINA_RERANKER_MIN_BYTES)
        verify_gguf_file(projector, JINA_RERANKER_PROJECTOR_MIN_BYTES)
        return [gguf, projector]
    except (FileNotFoundError, ValueError):
        return download_jina_reranker(MODEL_PATH)


def verify_all_models() -> None:
    """Runtime startup: verify baked models exist — no Hub download."""
    _verify_liquid_models()
    _verify_gliner2_model()
    _verify_qwen3_model()
    _verify_jina_retrieval_gguf()
    _verify_jina_reranker()


def _verify_liquid_models() -> list[Path]:
    paths: list[Path] = []
    for key, meta in LIQUID_MODELS.items():
        dest = expected_liquid_path(key)
        verify_gguf_file(dest, int(meta["min_bytes"]))
        paths.append(dest)
    return paths


def _verify_gliner2_model() -> Path:
    dest = expected_gliner2_path()
    verify_pretrained_model_dir(dest)
    return dest


def _verify_qwen3_model() -> Path:
    dest = expected_qwen3_path()
    verify_pretrained_model_dir(dest, require_tokenizer=True)
    return dest


def _verify_jina_retrieval_gguf() -> Path:
    dest = expected_jina_retrieval_path()
    verify_gguf_file(dest, JINA_TEXT_MIN_BYTES)
    return dest


def _verify_jina_reranker() -> list[Path]:
    gguf = expected_jina_reranker_path()
    projector = expected_jina_reranker_projector_path()
    verify_gguf_file(gguf, JINA_RERANKER_MIN_BYTES)
    verify_gguf_file(projector, JINA_RERANKER_PROJECTOR_MIN_BYTES)
    return [gguf, projector]


def download_all_models() -> None:
    """Build-time: download any missing models into MODEL_PATH."""
    _ensure_liquid_models()
    _ensure_gliner2_model()
    _ensure_qwen3_model()
    _ensure_jina_retrieval_gguf()
    _ensure_jina_reranker()


def ensure_model() -> None:
    """Worker startup: fail fast if image models are incomplete."""
    verify_all_models()


def main() -> None:
    MODEL_PATH.mkdir(parents=True, exist_ok=True)
    try:
        for path in _ensure_liquid_models():
            print(f"LiquidAI model ready at {path}")
        gliner2 = _ensure_gliner2_model()
        print(f"GLiNER2 model ready at {gliner2}")
        qwen3 = _ensure_qwen3_model()
        print(f"Qwen3-8B model ready at {qwen3}")
        retrieval = _ensure_jina_retrieval_gguf()
        print(f"Jina retrieval GGUF ready at {retrieval}")
        for path in _ensure_jina_reranker():
            print(f"Jina reranker asset ready at {path}")
    except Exception as exc:
        print(f"Model ensure failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
