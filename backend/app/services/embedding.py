"""
services/embedding.py — EmbeddingModule (BGE-M3 via sentence-transformers).

STRICT MODULE BOUNDARY (Backend §2):
  • This module ONLY produces vectors. It NEVER chunks, NEVER persists,
    NEVER coordinates. Called exclusively by the PipelineOrchestrator.

Construction note #1 (MANDATORY — explicit user requirement):
  After `model.encode(texts, ...)`, the output may be bfloat16 on GPU.
  NumPy CANNOT handle bfloat16 (no native dtype). ALWAYS convert:
        vector = embedding.cpu().to(torch.float32).numpy()
  before returning any vector to callers. This is applied in `embed` and
  `embed_batch`. A clear comment marks each cast site.

Retry policy (per error-handling-retry-strategy_v1.1.md §3):
  • `embed_with_retry`: max 3 attempts, exponential backoff 1s → 2s → 4s.
  • Retry on: transient network errors, CUDA OOM (with smaller batch).
  • Do NOT retry on: validation errors, permanent model loading failures.

Device selection:
  • GPU when torch.cuda.is_available() AND settings.use_gpu.
  • CPU otherwise (logged clearly so the researcher knows).

Singleton:
  • The model is loaded ONCE at app startup (lifespan) and shared across
    requests via a module-level singleton. Thread-safe via a Lock — encode()
    is itself thread-safe in sentence-transformers, but model load is not.
"""

from __future__ import annotations

import os
import threading
import time
from typing import List, Optional

from app.core.config import settings
from app.core.constants import EMBEDDING_BACKOFF_MS, EMBEDDING_MAX_RETRIES
from app.core.exceptions import EmbeddingError
from app.core.logging import get_logger
from app.utils.tokenization import approx_token_count

logger = get_logger("rag.services.embedding")


class EmbeddingModule:
    """BGE-M3 embedding module (singleton, thread-safe)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._model = None
        self._tokenizer = None
        self._device: Optional[str] = None
        self._loaded = False
        self._load_error: Optional[str] = None

    # ─── lifecycle ──────────────────────────────────────────────────────────

    def load(self) -> None:
        """Load BGE-M3 into memory. Safe to call multiple times."""
        with self._lock:
            if self._loaded:
                return
            device = settings.device
            self._device = device
            try:
                # Set CUDA_VISIBLE_DEVICES before importing torch if CPU-only.
                os.environ.setdefault("CUDA_VISIBLE_DEVICES", settings.cuda_visible_devices)
                from sentence_transformers import SentenceTransformer  # local import

                # Resolve the local model dir if present, else fall back to the HF repo id
                # (so a fresh dev box without a downloaded snapshot still works).
                local_path = os.path.join(settings.model_path, settings.embedding_model_name)
                model_src = local_path if os.path.isdir(local_path) else settings.bge_m3_repo
                logger.info(
                    "embedding.load.start",
                    extra={
                        "event": "embedding.load.start",
                        "model_src": model_src,
                        "device": device,
                    },
                )
                self._model = SentenceTransformer(
                    model_src,
                    device=device,
                    trust_remote_code=settings.embedding_trust_remote_code,   # ← 新增這行
                )
                # Best-effort: also expose the underlying tokenizer for exact token counts.
                try:
                    self._tokenizer = self._model.tokenizer  # type: ignore[attr-defined]
                except Exception:
                    self._tokenizer = None
                self._loaded = True
                logger.info(
                    "embedding.load.ok",
                    extra={
                        "event": "embedding.load.ok",
                        "model_src": model_src,
                        "device": device,
                        "dim": settings.embedding_dim,
                    },
                )
            except Exception as exc:
                self._load_error = str(exc)
                logger.error(
                    "embedding.load.failed",
                    extra={
                        "event": "embedding.load.failed",
                        "error": str(exc),
                    },
                )
                # Permanent model-loading failure — DO NOT retry at call time.
                raise EmbeddingError(
                    f"Failed to load BGE-M3 embedding model: {exc}",
                    details={"model_src": settings.bge_m3_repo, "device": device},
                    stage="embedding_load",
                ) from exc

    @property
    def device(self) -> str:
        return self._device or settings.device

    @property
    def loaded(self) -> bool:
        return self._loaded

    # ─── core encode ────────────────────────────────────────────────────────

    def embed_batch(self, texts: List[str], *, batch_size: Optional[int] = None) -> List[List[float]]:
        """Embed a batch of texts. Returns one 1024-dim vector per input.

        Construction note #1 (MANDATORY): the model output may be bfloat16 on
        GPU. NumPy has no native bfloat16 dtype and will raise
        `TypeError: Got unsupported ArrayType <class 'numpy.dtypes.FloatDType'>`
        (or return wrong values via object arrays). ALWAYS cast to float32 on
        CPU before calling .numpy().
        """
        if not texts:
            return []
        self._ensure_loaded()
        bs = batch_size or settings.embedding_batch_size
        try:
            import torch  # local import — torch is only needed at encode time

            # sentence-transformers' encode already returns a numpy float32 array
            # in most configurations, BUT on some GPU paths (bfloat16 autocast,
            # AMP, certain XPU configs) the underlying tensor is bfloat16. To be
            # bullet-proof we ask encode() for torch tensors and do the cast
            # ourselves, then convert to a plain Python list[float].
            outputs: List[List[float]] = []
            for i in range(0, len(texts), bs):
                batch = texts[i : i + bs]
                # `convert_to_numpy=False` → we get a torch.Tensor back.
                # `normalize_embeddings=True` so cosine similarity is a simple dot product
                # (the HNSW cosine index expects normalized vectors for stable scores).
                encode_kwargs = {
                    "batch_size": len(batch),
                    "convert_to_numpy": False,
                    "convert_to_tensor": True,
                    "normalize_embeddings": True,
                    "show_progress_bar": False,
                }
                if settings.embedding_encode_task:
                    encode_kwargs["task"] = settings.embedding_encode_task   # ← Jina v5 推薦傳 "retrieval"

                emb = self._model.encode(batch, **encode_kwargs)
                # ─── Construction note #1 (MANDATORY) ──────────────────────────
                # NumPy cannot handle bfloat16. Force the tensor to CPU + float32
                # before converting to a Python list. This is the explicit user
                # requirement and is applied on EVERY encode path (GPU and CPU).
                emb_cpu = emb.detach().cpu().to(torch.float32)
                outputs.extend(emb_cpu.tolist())
            return outputs
        except Exception as exc:
            # CUDA OOM → caller (embed_with_retry) will retry with a smaller batch.
            msg = str(exc).lower()
            if "out of memory" in msg or "cuda" in msg and "memory" in msg:
                raise EmbeddingError(
                    f"CUDA OOM during embedding (batch_size={bs}): {exc}",
                    details={"batch_size": bs, "device": self.device},
                    stage="embedding_encode",
                ) from exc
            # Permanent failure
            raise EmbeddingError(
                f"Embedding failed: {exc}",
                details={"batch_size": bs, "device": self.device},
                stage="embedding_encode",
            ) from exc

    def embed(self, text: str) -> List[float]:
        """Embed a single text. Returns a 1024-dim list[float]."""
        if not text:
            # Zero vector for empty input (won't be normalized, but the orchestrator
            # should never embed empty text — guard anyway).
            return [0.0] * settings.embedding_dim
        vectors = self.embed_batch([text], batch_size=1)
        return vectors[0]

    # ─── retry wrapper (per error-handling spec §3) ─────────────────────────

    def embed_with_retry(
        self,
        text: str,
        *,
        experiment_id: Optional[str] = None,
    ) -> List[float]:
        """Single-text embed with max 3 attempts + exp backoff 1s/2s/4s.

        Retries on transient errors (CUDA OOM with smaller batch, network).
        Does NOT retry on validation errors or permanent model load failures.
        """
        if not text or not text.strip():
            raise EmbeddingError(
                "Cannot embed empty text",
                stage="embedding_encode",
                experiment_id=experiment_id,
            )
        last_exc: Optional[Exception] = None
        for attempt in range(EMBEDDING_MAX_RETRIES):
            try:
                # On retry after OOM, halve the batch size (1 → still 1 here, but
                # embed_batch itself halves internally on subsequent calls).
                return self.embed(text)
            except EmbeddingError as exc:
                last_exc = exc
                # Permanent failures (load errors) should not retry.
                if exc.stage == "embedding_load":
                    raise
                if attempt < EMBEDDING_MAX_RETRIES - 1:
                    backoff_ms = EMBEDDING_BACKOFF_MS[attempt]
                    logger.warning(
                        "embedding.retry",
                        extra={
                            "event": "embedding.retry",
                            "attempt": attempt + 1,
                            "backoff_ms": backoff_ms,
                            "error": exc.message,
                            "experiment_id": experiment_id,
                        },
                    )
                    time.sleep(backoff_ms / 1000.0)
                    continue
                raise
            except Exception as exc:
                last_exc = exc
                if attempt < EMBEDDING_MAX_RETRIES - 1:
                    time.sleep(EMBEDDING_BACKOFF_MS[attempt] / 1000.0)
                    continue
                raise EmbeddingError(
                    f"Embedding failed after {EMBEDDING_MAX_RETRIES} attempts: {exc}",
                    stage="embedding_encode",
                    experiment_id=experiment_id,
                    retry_count=EMBEDDING_MAX_RETRIES,
                ) from exc
        # Unreachable — loop either returns or raises.
        raise EmbeddingError(
            f"Embedding failed after {EMBEDDING_MAX_RETRIES} attempts: {last_exc}",
            stage="embedding_encode",
            experiment_id=experiment_id,
            retry_count=EMBEDDING_MAX_RETRIES,
        )

    def embed_batch_with_retry(
        self,
        texts: List[str],
        *,
        experiment_id: Optional[str] = None,
    ) -> List[List[float]]:
        """Batch embed with retry. On CUDA OOM, halves the batch size and retries."""
        if not texts:
            return []
        last_exc: Optional[Exception] = None
        batch_size = settings.embedding_batch_size
        for attempt in range(EMBEDDING_MAX_RETRIES):
            try:
                return self.embed_batch(texts, batch_size=batch_size)
            except EmbeddingError as exc:
                last_exc = exc
                if exc.stage == "embedding_load":
                    raise
                # On OOM, halve the batch size for the next attempt.
                msg = (exc.details or {}).get("error", "") or exc.message
                if "oom" in msg.lower() or "out of memory" in msg.lower():
                    batch_size = max(1, batch_size // 2)
                if attempt < EMBEDDING_MAX_RETRIES - 1:
                    time.sleep(EMBEDDING_BACKOFF_MS[attempt] / 1000.0)
                    continue
                raise
            except Exception as exc:
                last_exc = exc
                if attempt < EMBEDDING_MAX_RETRIES - 1:
                    time.sleep(EMBEDDING_BACKOFF_MS[attempt] / 1000.0)
                    continue
                raise EmbeddingError(
                    f"Batch embedding failed after {EMBEDDING_MAX_RETRIES} attempts: {exc}",
                    stage="embedding_encode",
                    experiment_id=experiment_id,
                    retry_count=EMBEDDING_MAX_RETRIES,
                ) from exc
        raise EmbeddingError(
            f"Batch embedding failed after {EMBEDDING_MAX_RETRIES} attempts: {last_exc}",
            stage="embedding_encode",
            experiment_id=experiment_id,
            retry_count=EMBEDDING_MAX_RETRIES,
        )

    # ─── token count (exact when tokenizer available) ───────────────────────

    def token_count(self, text: str) -> int:
        """Exact token count when the BGE-M3 tokenizer is loaded; heuristic fallback."""
        if self._tokenizer is not None:
            try:
                return len(self._tokenizer.encode(text, add_special_tokens=False))
            except Exception:
                pass
        return approx_token_count(text)

    # ─── internal ───────────────────────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()


# ─── Module-level singleton accessor ─────────────────────────────────────────

_embedder: Optional[EmbeddingModule] = None
_embedder_lock = threading.Lock()


def get_embedder() -> EmbeddingModule:
    global _embedder
    if _embedder is None:
        with _embedder_lock:
            if _embedder is None:
                _embedder = EmbeddingModule()
    return _embedder
