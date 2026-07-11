from __future__ import annotations

import logging
import os
from typing import Any

import structlog


def configure_logging(service_name: str = "knowledgebase") -> None:
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level, logging.INFO)),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    structlog.contextvars.bind_contextvars(service=service_name)


def get_logger(name: str) -> Any:
    return structlog.get_logger(name)


def bind_trace_context(*, trace_id: str | None = None, span_id: str | None = None) -> None:
    ctx: dict[str, str] = {}
    if trace_id:
        ctx["trace_id"] = trace_id
    if span_id:
        ctx["span_id"] = span_id
    if ctx:
        structlog.contextvars.bind_contextvars(**ctx)


def clear_trace_context() -> None:
    structlog.contextvars.clear_contextvars()
