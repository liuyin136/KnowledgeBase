from __future__ import annotations

import os
from typing import Callable

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

_tracer = None
_provider = None
_current_span_id: str | None = None


def setup_otel(app: FastAPI) -> None:
    global _tracer, _provider
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    service_name = os.environ.get("OTEL_SERVICE_NAME", "knowledgebase-api")
    if not endpoint:
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces")
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _provider = provider
    _tracer = trace.get_tracer(service_name)
    app.add_middleware(OtelMiddleware)


def current_span_id() -> str | None:
    return _current_span_id


def shutdown_otel() -> None:
    global _provider
    if _provider is not None:
        _provider.shutdown()


class OtelMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        global _current_span_id
        from opentelemetry import trace
        from opentelemetry.propagate import extract
        from opentelemetry.trace import SpanKind

        ctx = extract(dict(request.headers))
        tracer = trace.get_tracer(os.environ.get("OTEL_SERVICE_NAME", "knowledgebase-api"))
        with tracer.start_as_current_span(
            f"{request.method} {request.url.path}",
            context=ctx,
            kind=SpanKind.SERVER,
        ) as span:
            span_ctx = span.get_span_context()
            _current_span_id = format(span_ctx.span_id, "016x") if span_ctx.is_valid else None
            response = await call_next(request)
            if _current_span_id:
                response.headers["X-Span-Id"] = _current_span_id
            return response
