"""
Collector implementations the mediator's AsyncQueueEmitter drains into.

I1: mediator and recorder talk over HTTP even in local dev — never a shared
import, never shared memory (Section 10). RecorderHttpCollector is that
HTTP client; NullCollector is a safe default for dev/tests when no recorder
is running (RECORDER_URL unset).
"""

from __future__ import annotations

import logging

import httpx

from common.schema import Session, Step

logger = logging.getLogger("blackbox.recorder.client")


class NullCollector:
    async def emit_session(self, session: Session) -> None:
        return None

    async def emit_step(self, step: Step) -> None:
        return None


class RecorderHttpCollector:
    """The mediator's only connection to the recorder is this HTTP client
    — matching the deployed shape even locally (I1, Section 10)."""

    def __init__(self, base_url: str, *, client: httpx.AsyncClient | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=5.0)

    async def emit_session(self, session: Session) -> None:
        try:
            resp = await self._client.post(
                f"{self._base_url}/sessions",
                content=session.model_dump_json(),
                headers={"content-type": "application/json"},
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            logger.exception("blackbox: failed to POST session to recorder")

    async def emit_step(self, step: Step) -> None:
        try:
            resp = await self._client.post(
                f"{self._base_url}/sessions/{step.session_id}/steps",
                content=step.model_dump_json(),
                headers={"content-type": "application/json"},
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            logger.exception("blackbox: failed to POST step to recorder")

    async def aclose(self) -> None:
        await self._client.aclose()
