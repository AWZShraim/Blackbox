"""
I2: the recorder never blocks the mediator. The mediator emits into an
in-memory queue; a separate asyncio task drains it into whatever sink is
configured (an HTTP client to the recorder, from M5 onward). Queue overflow
drops events and increments a counter — it never applies backpressure to
the mediator, which is the whole point: a tool call must never wait on a
database write.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Union

from common.interfaces import Collector
from common.schema import Session, Step

logger = logging.getLogger("blackbox.mediator.emit")

_Event = Union[Session, Step]


class AsyncQueueEmitter:
    """Implements Collector. `emit_session` / `emit_step` never await on
    I/O — they only touch an in-process queue via put_nowait, so nothing
    downstream of this class can make a tool call block."""

    def __init__(self, sink: Collector, *, maxsize: int = 10_000) -> None:
        self._sink = sink
        self._queue: asyncio.Queue[_Event] = asyncio.Queue(maxsize=maxsize)
        self._drop_count = 0
        self._drain_task: asyncio.Task | None = None

    @property
    def drop_count(self) -> int:
        return self._drop_count

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    def start(self) -> None:
        if self._drain_task is None:
            self._drain_task = asyncio.create_task(self._drain())

    async def stop(self, *, drain_remaining: bool = True) -> None:
        if drain_remaining:
            await self._queue.join()
        if self._drain_task is not None:
            self._drain_task.cancel()
            try:
                await self._drain_task
            except asyncio.CancelledError:
                pass
            self._drain_task = None

    async def emit_session(self, session: Session) -> None:
        self._put(session)

    async def emit_step(self, step: Step) -> None:
        self._put(step)

    def _put(self, event: _Event) -> None:
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            self._drop_count += 1
            logger.warning(
                "blackbox: trace queue full, dropping event (total dropped=%d)", self._drop_count
            )

    async def _drain(self) -> None:
        while True:
            event = await self._queue.get()
            try:
                if isinstance(event, Session):
                    await self._sink.emit_session(event)
                else:
                    await self._sink.emit_step(event)
            except Exception:  # noqa: BLE001 - a delivery failure must not kill the drain loop
                logger.exception("blackbox: failed to deliver trace event to sink")
            finally:
                self._queue.task_done()
