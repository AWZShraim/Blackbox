"""StdoutExporter: local dev / CI default (Section 4's Exporter seam).
Prints the exact span shape otel_mapping.py produces, so what you see
locally is what OtlpExporter would ship to a real collector."""

from __future__ import annotations

import json
import logging

from common.schema import Session, Step
from recorder.otel_mapping import attributes_for_step, events_for_step, span_name_for_step

logger = logging.getLogger("blackbox.recorder.exporters.stdout")


class StdoutExporter:
    async def export_session(self, session: Session) -> None:
        logger.info("session %s status=%s", session.session_id, session.status.value)

    async def export_step(self, session: Session, step: Step) -> None:
        span = {
            "name": span_name_for_step(step),
            "attributes": attributes_for_step(session, step),
            "events": events_for_step(step),
        }
        print(json.dumps(span, default=str))
