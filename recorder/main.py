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
from sse_starlette.sse import EventSourceResponse

from common.schema import Session, SessionStatus, Step, StepType
from detector.baseline import BaselineStore
from detector.engine import run_detectors
from recorder.broadcast import SessionBroadcaster
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


def create_app(
    *, store: PostgresStore | None = None, archive=None, exporters=None,
    baseline_store: BaselineStore | None = None, run_detection: bool = True,
) -> FastAPI:
    database_url = os.environ.get(
        "DATABASE_URL", "postgresql+asyncpg://blackbox:blackbox@localhost:5432/blackbox"
    )
    store = store or PostgresStore(database_url)

    if archive is None:
        bucket = os.environ.get("ARCHIVE_S3_BUCKET")
        archive = S3ObjectLockArchive(bucket) if bucket else LocalDiskArchive(Path("recorder/.archive"))

    active_exporters = exporters if exporters is not None else [StdoutExporter()]

    if baseline_store is None:
        baseline_dir = os.environ.get("BLACKBOX_BASELINE_DIR")
        baseline_store = BaselineStore(Path(baseline_dir)) if baseline_dir else None

    queue: asyncio.Queue[_Event] = asyncio.Queue(maxsize=20_000)
    state = {"drop_count": 0, "drain_task": None}
    broadcaster = SessionBroadcaster()

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
                await _process_event(
                    event, store=store, archive=archive, exporters=active_exporters,
                    baseline_store=baseline_store, run_detection=run_detection, broadcaster=broadcaster,
                )
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

    @app.get("/sessions/{session_id}/stream")
    async def stream_session(session_id: str):
        """I9: live and recorded traces render over the same channel. This
        sends the full trace so far immediately, then tails new events as
        they land — a viewer opening this mid-run and one opening it after
        the fact see the same event shapes in the same order, just with
        different timing. The replay endpoint (M10) emits over this exact
        shape with synthetic timing instead of real."""
        sid = uuid.UUID(session_id)

        async def event_gen():
            trace = await store.get_trace(sid)
            if trace is None:
                yield {"event": "error", "data": "unknown session"}
                return
            yield {"event": "session", "data": trace.session.model_dump_json()}
            for step in trace.steps:
                yield {"event": "step", "data": step.model_dump_json()}

            live_terminal = {"completed", "failed", "terminated"}
            if trace.session.status.value in live_terminal:
                return  # nothing more will ever arrive for a session that's already done

            sub = broadcaster.subscribe(sid)
            try:
                while True:
                    event = await sub.get()
                    if isinstance(event, Session):
                        yield {"event": "session", "data": event.model_dump_json()}
                        if event.status.value in live_terminal:
                            return
                    else:
                        yield {"event": "step", "data": event.model_dump_json()}
            finally:
                broadcaster.unsubscribe(sid, sub)

        return EventSourceResponse(event_gen())

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "queue_depth": queue.qsize(), "drop_count": state["drop_count"]}

    return app


async def _process_event(
    event: _Event, *, store: PostgresStore, archive, exporters: list,
    baseline_store: BaselineStore | None, run_detection: bool, broadcaster: SessionBroadcaster,
) -> None:
    if isinstance(event, Session):
        await store.upsert_session(event)
        for exporter in exporters:
            await exporter.export_session(event)
        broadcaster.publish(event.session_id, event)
        if event.status in ARCHIVE_ON_STATUSES:
            trace = await store.get_trace(event.session_id)
            if trace is not None:
                await archive.archive_trace(trace)
        return

    await store.insert_step(event)
    session = await store.get_session(event.session_id)
    if session is not None:
        for exporter in exporters:
            await exporter.export_step(session, event)
    broadcaster.publish(event.session_id, event)

    # Detection runs on the trace stream (Section 6.4), not in the
    # mediator's request path — this is that stream. Skip re-running it
    # off the flags it just produced: nothing in detector/detectors/*
    # takes a detection_flag step as an input signal, so this can't loop,
    # but there's no reason to pay for the trace fetch either.
    if run_detection and event.type != StepType.detection_flag and session is not None:
        await _run_detection_and_persist(
            session.session_id, store=store, exporters=exporters,
            baseline_store=baseline_store, broadcaster=broadcaster,
        )


async def _run_detection_and_persist(
    session_id, *, store: PostgresStore, exporters: list,
    baseline_store: BaselineStore | None, broadcaster: SessionBroadcaster,
) -> None:
    trace = await store.get_trace(session_id)
    if trace is None:
        return

    already_flagged = {
        (s.payload.detector_id, s.parent_step_id)
        for s in trace.steps
        if s.type == StepType.detection_flag
    }

    agent_baseline = baseline_store.load("agent", trace.session.agent_id) if baseline_store else None
    human_baseline = baseline_store.load("human", trace.session.human_id) if baseline_store else None

    new_flag_steps = [
        s for s in run_detectors(trace, agent_baseline=agent_baseline, human_baseline=human_baseline)
        if (s.payload.detector_id, s.parent_step_id) not in already_flagged
    ]
    for flag_step in new_flag_steps:
        await store.insert_step(flag_step)
        session = trace.session
        for exporter in exporters:
            await exporter.export_step(session, flag_step)
        broadcaster.publish(session_id, flag_step)


app = create_app()
