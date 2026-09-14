"""OtlpExporter: real OpenTelemetry spans shipped over OTLP/HTTP, built from
otel_mapping.py (I5: content in span events, never span attributes). OTel
attribute values must be primitives or homogeneous primitive sequences;
`_flatten` JSON-encodes anything else rather than silently dropping it —
losing data at export time is exactly what I5 exists to prevent."""

from __future__ import annotations

import json
from typing import Any

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from common.schema import Session, Step
from recorder.otel_mapping import attributes_for_step, events_for_step, span_name_for_step


def _flatten(attrs: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in attrs.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            out[key] = value
        elif isinstance(value, list) and all(isinstance(v, (str, int, float, bool)) for v in value):
            out[key] = value
        else:
            out[key] = json.dumps(value, default=str)
    return out


class OtlpExporter:
    def __init__(self, endpoint: str, *, service_name: str = "blackbox-recorder") -> None:
        resource = Resource.create({"service.name": service_name})
        self._provider = TracerProvider(resource=resource)
        self._provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        self._tracer = self._provider.get_tracer("blackbox.recorder")

    async def export_session(self, session: Session) -> None:
        return None  # sessions surface via attributes on their steps' spans, not a span of their own

    async def export_step(self, session: Session, step: Step) -> None:
        attrs = _flatten(attributes_for_step(session, step))
        with self._tracer.start_as_current_span(span_name_for_step(step), attributes=attrs) as span:
            for event in events_for_step(step):
                span.add_event(event["name"], attributes=_flatten(event["attributes"]))

    def shutdown(self) -> None:
        self._provider.shutdown()
