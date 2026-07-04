"""
utils/timing.py — High-resolution monotonic timers + a `timed` async/sync helper.

Mirrors src/lib/rag/utils.ts (nowMs / timed / timedSync).
"""

from __future__ import annotations

import time
from typing import Awaitable, Callable, Tuple, TypeVar

T = TypeVar("T")


def now_ms() -> float:
    """Monotonic millisecond timestamp."""
    return time.perf_counter() * 1000.0


async def timed(fn: Callable[[], Awaitable[T]]) -> Tuple[T, float]:
    """Await `fn`, return (result, elapsed_ms)."""
    start = now_ms()
    result = await fn()
    return result, now_ms() - start


def timed_sync(fn: Callable[[], T]) -> Tuple[T, float]:
    """Run sync `fn`, return (result, elapsed_ms)."""
    start = now_ms()
    result = fn()
    return result, now_ms() - start
