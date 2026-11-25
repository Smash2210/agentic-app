"""OpenTelemetry tracing to a local file (spec 005 FR-505).

ADK already creates spans for the agent run, every model call and every tool call. setup_tracing()
installs an SDK provider that writes every finished span as one JSON line to OTEL_TRACE_FILE, so a
run can be inspected offline (scripts/show_trace.py) without any hosted service. Our own code adds a
span per tool attempt and an event per guardrail decision through `tracer`.
"""

import os
import threading

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult

tracer = trace.get_tracer("agentic_app")
_lock = threading.Lock()


class JsonLinesExporter(SpanExporter):
    def __init__(self, path: str):
        self.path = path

    def export(self, spans) -> SpanExportResult:
        with _lock, open(self.path, "a", encoding="utf-8") as f:
            for span in spans:
                f.write(span.to_json(indent=None) + "\n")
        return SpanExportResult.SUCCESS


def setup_tracing(path: str | None = None) -> str | None:
    """Export spans to `path` (or OTEL_TRACE_FILE). Returns the path, or None if tracing is off.
    Call once per process, before the agent runs."""
    path = path or os.getenv("OTEL_TRACE_FILE")
    if not path:
        return None
    provider = TracerProvider(resource=Resource.create({"service.name": "agentic-app"}))
    provider.add_span_processor(SimpleSpanProcessor(JsonLinesExporter(path)))
    trace.set_tracer_provider(provider)
    return path


def event(name: str, **attributes) -> None:
    """Record a guardrail (or other) decision on the current span, if one is recording."""
    trace.get_current_span().add_event(name, {k: str(v) for k, v in attributes.items()})
