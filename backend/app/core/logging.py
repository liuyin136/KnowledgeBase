"""
core/logging.py — Structured JSON logging with experiment_id / correlation_id.

Per error-handling-retry-strategy_v1.1.md §4, every error must be logged with:
  {
    "event": "pipeline.error",
    "experiment_id": "...",
    "stage": "embedding" | "chunking" | "neo4j_write" | "retrieval",
    "error_code": "EMBEDDING_FAILED",
    "error_message": "...",
    "retry_count": 2
  }

Implementation: a thin wrapper around stdlib logging that emits one JSON object
per log line (so docker logs / journald can parse them). We avoid hard-depending
on structlog's processor chain to keep the runtime surface minimal, but structlog
is also supported (the dependency is in requirements.txt).

A contextvars-based correlation scope (`bind_experiment_id`, `bind_correlation_id`)
lets deep call sites tag their log records without threading the ids through every
function signature.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
import time
from typing import Any, Dict, Optional

# Contextvars — propagate per-request / per-job ids through async call stacks.
_experiment_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "experiment_id", default=None
)
_correlation_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "correlation_id", default=None
)


def bind_experiment_id(experiment_id: Optional[str]) -> contextvars.Token:
    return _experiment_id_var.set(experiment_id)


def bind_correlation_id(correlation_id: Optional[str]) -> contextvars.Token:
    return _correlation_id_var.set(correlation_id)


def reset_experiment_id(token: contextvars.Token) -> None:
    _experiment_id_var.reset(token)


def reset_correlation_id(token: contextvars.Token) -> None:
    _correlation_id_var.reset(token)


class JSONFormatter(logging.Formatter):
    """Emit each LogRecord as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": time.time(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Contextvar fields
        exp = _experiment_id_var.get()
        corr = _correlation_id_var.get()
        if exp is not None:
            payload["experiment_id"] = exp
        if corr is not None:
            payload["correlation_id"] = corr
        # Attach well-known extras (anything the caller passed via logger.info(..., extra={...})).
        for k, v in record.__dict__.items():
            if k in {
                "args", "asctime", "created", "exc_info", "exc_text", "filename",
                "funcName", "levelname", "levelno", "lineno", "module", "msecs",
                "message", "msg", "name", "pathname", "process", "processName",
                "relativeCreated", "stack_info", "thread", "threadName", "taskName",
            }:
                continue
            if k.startswith("_"):
                continue
            payload[k] = v
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> logging.Logger:
    """Configure root + uvicorn loggers to emit JSON."""
    root = logging.getLogger()
    root.setLevel(level)
    # Replace any pre-existing handlers (uvicorn installs its own).
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)
    # Silence noisy libs that aren't useful in JSON form
    for noisy in ("urllib3", "neo4j", "httpx", "httpcore", "sentence_transformers", "transformers"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return root


def get_logger(name: str = "rag") -> logging.Logger:
    return logging.getLogger(name)


# ─── Structured event helpers ─────────────────────────────────────────────────


def log_pipeline_error(
    logger: logging.Logger,
    *,
    stage: str,
    error_code: str,
    error_message: str,
    experiment_id: Optional[str] = None,
    retry_count: Optional[int] = None,
    **extra: Any,
) -> None:
    """Emit a structured pipeline.error event (per error-handling spec §4)."""
    payload: Dict[str, Any] = {
        "event": "pipeline.error",
        "stage": stage,
        "error_code": error_code,
        "error_message": error_message,
    }
    if experiment_id is not None:
        payload["experiment_id"] = experiment_id
    if retry_count is not None:
        payload["retry_count"] = retry_count
    payload.update(extra)
    logger.error(payload.pop("error_message", error_message), extra=payload)


def log_pipeline_event(
    logger: logging.Logger,
    event: str,
    message: str,
    **fields: Any,
) -> None:
    """Emit a structured pipeline.<event> info record."""
    payload: Dict[str, Any] = {"event": event}
    payload.update(fields)
    logger.info(message, extra=payload)
