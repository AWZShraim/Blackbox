"""Shared test doubles. Implement the real Protocols from common/interfaces.py
so a structural (isinstance) check against them passes — these are not
stand-ins for production Collector/Exporter code, only for tests that need a
fast, in-memory Collector rather than an HTTP round trip to the recorder."""

from __future__ import annotations

from common.schema import Session, Step


class InMemoryCollector:
    def __init__(self) -> None:
        self.sessions: list[Session] = []
        self.steps: list[Step] = []

    async def emit_session(self, session: Session) -> None:
        self.sessions.append(session)

    async def emit_step(self, step: Step) -> None:
        self.steps.append(step)
