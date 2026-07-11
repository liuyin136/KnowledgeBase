from __future__ import annotations

import functools
import os
import uuid
from typing import Any, Callable, TypeVar

from app.core.logging import bind_trace_context, clear_trace_context

F = TypeVar("F", bound=Callable[..., Any])

_provider_initialized = False


def _ensure_tracer_provider() -> None:
    global _provider_initialized
    if _provider_initialized:
        return
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if not endpoint:
        _provider_initialized = True
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    service_name = os.environ.get("OTEL_SERVICE_NAME", "knowledgebase-worker")
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    exporter = OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces")
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _provider_initialized = True


def _resolve_traceparent(explicit: str) -> str:
    if explicit:
        return explicit
    try:
        from rq import get_current_job

        job = get_current_job()
        if job and job.meta:
            return str(job.meta.get("traceparent") or "")
    except Exception:
        pass
    return ""


def worker_trace(task_name: str):
    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            traceparent = _resolve_traceparent("")
            _ensure_tracer_provider()

            span_id: str | None = None
            trace_id: str | None = None
            if traceparent:
                parts = traceparent.split("-")
                if len(parts) >= 4:
                    trace_id, span_id = parts[1], parts[2]

            try:
                from opentelemetry import trace
                from opentelemetry.propagate import extract

                ctx = extract({"traceparent": traceparent}) if traceparent else None
                tracer = trace.get_tracer(os.environ.get("OTEL_SERVICE_NAME", "knowledgebase-worker"))
                with tracer.start_as_current_span(task_name, context=ctx) as span:
                    sc = span.get_span_context()
                    if sc.is_valid:
                        span_id = format(sc.span_id, "016x")
                        trace_id = format(sc.trace_id, "032x")
                    bind_trace_context(trace_id=trace_id, span_id=span_id)
                    return fn(*args, **kwargs)
            except Exception:
                bind_trace_context(trace_id=trace_id, span_id=span_id or uuid.uuid4().hex[:16])
                return fn(*args, **kwargs)
            finally:
                clear_trace_context()

        return wrapper  # type: ignore[return-value]

    return decorator
