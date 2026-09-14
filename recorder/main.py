"""
The recorder (Section 6.3): a separate process from the mediator (I1).
Receives events over HTTP — never in the mediator's request path — queues
them internally so its own HTTP handlers never block on Postgres, writes to
Postgres (the hot store), archives terminal/contained sessions to S3, and
exports OTel spans. There is no code path here that stops accepting events
for a session because its status changed — that is exactly what I1 forbids.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Union

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

from common.schema import Session, SessionStatus, Step
from recorder.exporters.stdout_exporter import StdoutExporter
from recorder.store.postgres import PostgresStore
from recorder.store.s3_archive import LocalDiskArchive, S3ObjectLockArchive

load_dotenv()
logger = logging.getLogger("blackbox.recorder")

# A session archives once it stops being "live" — contained sessions still
# archive here even though they keep accepting post-containment events
# (I1); a later terminal transition simply archives again.
ARCHIVE_ON_STATUSES = {
    SessionStatus.completed, SessionStatus.failed,
    SessionStatus.terminated, SessionStatus.contained,
}

_Event = Union[Session, Step]


def create_app(*, store: PostgresStore | None = None, archive=None, exporters=None) -> FastAPI:
    database_url = os.environ.get(
        "DATABASE_URL", "postgresql+asyncpg://blackbox:blackbox@localhost:5432/blackbox"
    )
    store = store or PostgresStore(database_url)

    if archive is None:
        bucket = os.environ.get("ARCHIVE_S3_BUCKET")
        archive = S3ObjectLockArchive(bucket) if bucket else LocalDiskArchive(Path("recorder/.archive"))

    active_exporters = exporters if exporters is not None else [StdoutExporter()]

    queue: asyncio.Queue[_Event] = asyncio.Queue(maxsize=20_000)
    state = {"drop_count": 0, "drain_task": None}

    def enqueue(event: _Event) -> None:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            state["drop_count"] += 1
            logger.warning(
                "blackbox recorder: queue full, dropping event (total dropped=%d)", state["drop_count"]
            )

    async def drain() -> None:
        while True:
            event = await queue.get()
            try:
                await _process_event(event, store=store, archive=archive, exporters=active_exporters)
            except Exception:  # noqa: BLE001 - one bad event must not kill the drain loop
                logger.exception("blackbox recorder: failed to process event")
            finally:
                queue.task_done()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await store.create_tables()
        state["drain_task"] = asyncio.create_task(drain())
        yield
        state["drain_task"].cancel()
        try:
            await state["drain_task"]
        except asyncio.CancelledError:
            pass
        await store.dispose()

    app = FastAPI(title="Blackbox Recorder", lifespan=lifespan)
    app.state.store = store

    @app.post("/sessions", status_code=202)
    async def post_session(session: Session) -> dict:
        enqueue(session)
        return {"accepted": True}

    @app.post("/sessions/{session_id}/steps", status_code=202)
    async def post_step(session_id: str, step: Step) -> dict:
        if str(step.session_id) != session_id:
            raise HTTPException(status_code=400, detail="session_id in path does not match step body")
        enqueue(step)
        return {"accepted": True}

    @app.get("/sessions/{session_id}")
    async def get_session_trace(session_id: str) -> dict:
        trace = await store.get_trace(uuid.UUID(session_id))
        if trace is None:
            raise HTTPException(status_code=404, detail="unknown session")
        return trace.model_dump(mode="json")

    @app.get("/sessions")
    async def list_sessions(
        human_id: str | None = None, agent_id: str | None = None,
        scenario_id: str | None = None, limit: int = 50,
    ) -> list[dict]:
        sessions = await store.list_sessions(
            human_id=human_id, agent_id=agent_id, scenario_id=scenario_id, limit=limit
        )
        return [s.model_dump(mode="json") for s in sessions]

    @app.get("/search")
    async def search_by_content_identifier(identifier: str, limit: int = 100) -> list[dict]:
        steps = await store.search_steps_by_content_identifier(identifier, limit=limit)
        return [s.model_dump(mode="json") for s in steps]

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "queue_depth": queue.qsize(), "drop_count": state["drop_count"]}

    return app


async def _process_event(event: _Event, *, store: PostgresStore, archive, exporters: list) -> None:
    if isinstance(event, Session):
        await store.upsert_session(event)
        for exporter in exporters:
            await exporter.export_session(event)
        if event.status in ARCHIVE_ON_STATUSES:
            trace = await store.get_trace(event.session_id)
            if trace is not None:
                await archive.archive_trace(trace)
    else:
        await store.insert_step(event)
        session = await store.get_session(event.session_id)
        if session is not None:
            for exporter in exporters:
                await exporter.export_step(session, event)


app = create_app()
