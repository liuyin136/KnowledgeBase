from __future__ import annotations

import numpy as np


def matryoshka_truncate(vec: np.ndarray, k: int) -> np.ndarray:
    """Take first k dims of L2-normalized vector, then re-normalize."""
    t = np.asarray(vec[:k], dtype=np.float32)
    norm = float(np.linalg.norm(t))
    return t / norm if norm > 0 else t


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))
