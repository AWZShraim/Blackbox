"""
In-memory pub/sub so the recorder can live-tail a session to the
Investigator (I9: live and recorded traces render over the same channel).
Purely additive to the store — losing a subscriber's queue loses nothing
durable, since Postgres remains the source of truth; a client that
reconnects just re-fetches the full trace and resumes tailing from there.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Union

from common.schema import Session, Step

_Event = Union[Session, Step]


class SessionBroadcaster:
    def __init__(self) -> None:
        self._subscribers: dict[uuid.UUID, set[asyncio.Queue[_Event]]] = {}

    def subscribe(self, session_id: uuid.UUID) -> asyncio.Queue[_Event]:
        queue: asyncio.Queue[_Event] = asyncio.Queue(maxsize=1000)
        self._subscribers.setdefault(session_id, set()).add(queue)
        return queue

    def unsubscribe(self, session_id: uuid.UUID, queue: asyncio.Queue[_Event]) -> None:
        subs = self._subscribers.get(session_id)
        if subs is None:
            return
        subs.discard(queue)
        if not subs:
            self._subscribers.pop(session_id, None)

    def publish(self, session_id: uuid.UUID, event: _Event) -> None:
        for queue in self._subscribers.get(session_id, ()):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass  # a slow viewer misses a live tick; the next full fetch/reconnect catches up
