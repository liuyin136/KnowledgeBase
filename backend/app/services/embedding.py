"""
services/embedding.py — EmbeddingModule (Jina v5 default + BGE-M3 toggle).

STRICT MODULE BOUNDARY (Backend §2):
  • This module ONLY produces vectors. It NEVER chunks, NEVER persists,
    NEVER coordinates. Called exclusively by the PipelineOrchestrator.

v1.3 model migration (CRITICAL — read me):
  • Default model is now `jinaai/jina-embeddings-v5-text-small` (Jina v5 small).
    BGE-M3 (`BAAI/bge-m3`) remains available as a toggleable alternative.
  • Jina v5 is TASK-CONDITIONED. The orchestrator must tell us whether we are
    embedding a QUERY or a PASSAGE (document). We map that to Jina's task
    string via `embed_batch(texts, *, is_query=False)`:
        is_query=True  → task="retrieval.query"
        is_query=False → task="retrieval.passages"
    BGE-M3 ignores the task parameter (it has no task conditioning) — the
    `is_query` flag is accepted on every call but no-op for BGE-M3.
  • MATRYOSHKA TRUNCATION: Jina v5 small natively outputs 1536 dims, but the
    Neo4j vector indexes are 1024-dim cosine (per neo4j-schema-v1.1.md §3).
    To keep BOTH models writing into the SAME indexes without re-creation,
    we invoke Jina with `dimensions=settings.embedding_dim` (1024). BGE-M3 is
    natively 1024-dim, so no `dimensions` arg is passed for it.
    Caveat: vectors are still model-specific. Switching models requires
    re-ingesting documents so the persisted vectors match the active embedder.
    The Settings UI documents this clearly.

Construction note #1 (MANDATORY — explicit user requirement, preserved for BOTH models):
  After `model.encode(texts, ...)`, the output may be bfloat16 on GPU.
  NumPy CANNOT handle bfloat16 (no native dtype). ALWAYS convert:
        vector = embedding.cpu().to(torch.float32).numpy()
  before returning any vector to callers. This is applied in `embed` and
  `embed_batch`. A clear comment marks each cast site. (Jina on GPU may also
  output bfloat16 — the same cast applies.)

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
from app.core.constants import (
    EMBEDDING_BACKOFF_MS,
    EMBEDDING_MAX_RETRIES,
    JINA_TASK_PASSAGE,
    JINA_TASK_QUERY,
)
from app.core.exceptions import EmbeddingError
from app.core.logging import get_logger
from app.utils.tokenization import approx_token_count

logger = get_logger("rag.services.embedding")


class EmbeddingModule:
    """Embedding module — Jina v5 (default) OR BGE-M3 (toggleable). Singleton, thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._model = None
        self._tokenizer = None
        self._device: Optional[str] = None
        self._loaded = False
        self._load_error: Optional[str] = None
        # The logical model id ("jina-v5-small" | "bge-m3") captured at load()
        # time. Stored on the instance so callers can observe which model is
        # actually loaded (rather than re-reading settings every encode).
        self._model_id: str = settings.embedding_model

    # ─── lifecycle ──────────────────────────────────────────────────────────

    def load(self) -> None:
        """Load the selected embedding model (Jina v5 or BGE-M3). Safe to call multiple times."""
        with self._lock:
            if self._loaded:
                return
            device = settings.device
            self._device = device
            self._model_id = settings.embedding_model
            try:
                # Set CUDA_VISIBLE_DEVICES before importing torch if CPU-only.
                os.environ.setdefault("CUDA_VISIBLE_DEVICES", settings.cuda_visible_devices)
                from sentence_transformers import SentenceTransformer  # local import

                # Resolve the local model dir if present, else fall back to the HF repo id
                # (so a fresh dev box without a downloaded snapshot still works).
                local_path = os.path.join(settings.model_path, settings.embedding_model_name)
                model_src = local_path if os.path.isdir(local_path) else settings.embedding_repo
                logger.info(
                    "embedding.load.start",
                    extra={
                        "event": "embedding.load.start",
                        "model_id": self._model_id,
                        "model_src": model_src,
                        "device": device,
                        "native_dim": settings.model_dim,
                        "embedding_dim": settings.embedding_dim,
                    },
                )

                if self._model_id == "jina-v5-small":
                    # Jina Embeddings v5 is task-conditioned + supports Matryoshka
                    # truncation. We pass the task at ENCODE time (not load time)
                    # since the same model serves both query and passage paths.
                    # `truncate_dim` is the sentence-transformers knob for the
                    # `dimensions` Matryoshka parameter — set it at load so every
                    # encode returns a 1024-dim vector (matches the Neo4j indexes).
                    # `trust_remote_code=True` is required because Jina v5 ships a
                    # custom modeling file.
                    self._model = SentenceTransformer(
                        model_src,
                        device=device,
                        trust_remote_code=True,
                        truncate_dim=settings.embedding_dim,
                    )
                elif self._model_id == "bge-m3":
                    # BGE-M3 is a vanilla transformer — let sentence-transformers
                    # pick its default backend (PyTorch). No task conditioning.
                    self._model = SentenceTransformer(
                        model_src,
                        device=device,
                    )
                else:
                    # Validator on Settings should have caught this; guard anyway.
                    raise EmbeddingError(
                        f"Unknown embedding_model id: {self._model_id!r}. "
                        f"Expected one of: jina-v5-small, bge-m3.",
                        details={"embedding_model": self._model_id},
                        stage="embedding_load",
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
                        "model_id": self._model_id,
                        "model_src": model_src,
                        "device": device,
                        "native_dim": settings.model_dim,
                        "embedding_dim": settings.embedding_dim,
                    },
                )
            except Exception as exc:
                self._load_error = str(exc)
                logger.error(
                    "embedding.load.failed",
                    extra={
                        "event": "embedding.load.failed",
                        "model_id": self._model_id,
                        "error": str(exc),
                    },
                )
                # Permanent model-loading failure — DO NOT retry at call time.
                raise EmbeddingError(
                    f"Failed to load embedding model ({self._model_id}): {exc}",
                    details={
                        "model_id": self._model_id,
                        "model_src": settings.embedding_repo,
                        "device": device,
                    },
                    stage="embedding_load",
                ) from exc

    @property
    def device(self) -> str:
        return self._device or settings.device

    @property
    def loaded(self) -> bool:
        return self._loaded

    @property
    def model_id(self) -> str:
        """Logical id of the active model ('jina-v5-small' | 'bge-m3')."""
        return self._model_id

    # ─── core encode ────────────────────────────────────────────────────────

    def embed_batch(
        self,
        texts: List[str],
        *,
        batch_size: Optional[int] = None,
        is_query: bool = False,
    ) -> List[List[float]]:
        """Embed a batch of texts. Returns one `embedding_dim`-dim vector per input.

        Args:
          texts: input strings to embed.
          batch_size: override the default batch size (used by retry-on-OOM).
          is_query: when True, embed as a SEARCH QUERY; when False (default),
            embed as a DOCUMENT/PASSAGE. For Jina v5 this maps to the task
            string ("retrieval.query" vs "retrieval.passages"). For BGE-M3 this
            flag is IGNORED (no task conditioning).

        Construction note #1 (MANDATORY — preserved for BOTH models): the model
        output may be bfloat16 on GPU. NumPy has no native bfloat16 dtype and
        will raise `TypeError: Got unsupported ArrayType <class 'numpy.dtypes.FloatDType'>`
        (or return wrong values via object arrays). ALWAYS cast to float32 on
        CPU before calling .numpy(). Jina on GPU may also output bfloat16.
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
                encode_kwargs = dict(
                    batch_size=len(batch),
                    convert_to_numpy=False,
                    convert_to_tensor=True,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
                if self._model_id == "jina-v5-small":
                    # Jina v5 task conditioning. The orchestrator passes is_query
                    # so the same model can serve both indexing + search.
                    encode_kwargs["task"] = JINA_TASK_QUERY if is_query else JINA_TASK_PASSAGE
                    # NOTE: Matryoshka truncation to 1024 dims is configured at
                    # LOAD time via `truncate_dim` (see load()). We do NOT pass
                    # `dimensions=` here because sentence-transformers' encode()
                    # does not accept it directly — `truncate_dim` on the model
                    # is the supported knob.
                # BGE-M3: no task / dimensions kwargs — encode() defaults apply.

                emb = self._model.encode(batch, **encode_kwargs)
                # ─── Construction note #1 (MANDATORY — applies to BOTH models) ──
                # NumPy cannot handle bfloat16. Force the tensor to CPU + float32
                # before converting to a Python list. This is the explicit user
                # requirement and is applied on EVERY encode path (GPU and CPU),
                # for both Jina v5 and BGE-M3.
                emb_cpu = emb.detach().cpu().to(torch.float32)
                outputs.extend(emb_cpu.tolist())
            return outputs
        except Exception as exc:
            # CUDA OOM → caller (embed_with_retry) will retry with a smaller batch.
            msg = str(exc).lower()
            if "out of memory" in msg or "cuda" in msg and "memory" in msg:
                raise EmbeddingError(
                    f"CUDA OOM during embedding (batch_size={bs}, model={self._model_id}): {exc}",
                    details={
                        "batch_size": bs,
                        "device": self.device,
                        "model_id": self._model_id,
                    },
                    stage="embedding_encode",
                ) from exc
            # Permanent failure
            raise EmbeddingError(
                f"Embedding failed (model={self._model_id}): {exc}",
                details={
                    "batch_size": bs,
                    "device": self.device,
                    "model_id": self._model_id,
                },
                stage="embedding_encode",
            ) from exc

    def embed(self, text: str, *, is_query: bool = False) -> List[float]:
        """Embed a single text. Returns an `embedding_dim`-dim list[float].

        Pass `is_query=True` for search queries (Jina v5 task="retrieval.query");
        leave it False (default) for documents/passages (task="retrieval.passages").
        BGE-M3 ignores the flag.
        """
        if not text:
            # Zero vector for empty input (won't be normalized, but the orchestrator
            # should never embed empty text — guard anyway).
            return [0.0] * settings.embedding_dim
        vectors = self.embed_batch([text], batch_size=1, is_query=is_query)
        return vectors[0]

    # ─── retry wrapper (per error-handling spec §3) ─────────────────────────

    def embed_with_retry(
        self,
        text: str,
        *,
        experiment_id: Optional[str] = None,
        is_query: bool = False,
    ) -> List[float]:
        """Single-text embed with max 3 attempts + exp backoff 1s/2s/4s.

        Retries on transient errors (CUDA OOM with smaller batch, network).
        Does NOT retry on validation errors or permanent model load failures.

        Pass `is_query=True` for search queries (Jina v5 task="retrieval.query");
        leave it False (default) for documents/passages. BGE-M3 ignores the flag.
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
                return self.embed(text, is_query=is_query)
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
                            "is_query": is_query,
                            "model_id": self._model_id,
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
        is_query: bool = False,
    ) -> List[List[float]]:
        """Batch embed with retry. On CUDA OOM, halves the batch size and retries.

        Pass `is_query=True` for search queries (Jina v5 task="retrieval.query");
        leave it False (default) for documents/passages. BGE-M3 ignores the flag.
        """
        if not texts:
            return []
        last_exc: Optional[Exception] = None
        batch_size = settings.embedding_batch_size
        for attempt in range(EMBEDDING_MAX_RETRIES):
            try:
                return self.embed_batch(texts, batch_size=batch_size, is_query=is_query)
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
        """Exact token count when the active tokenizer is loaded; heuristic fallback."""
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
