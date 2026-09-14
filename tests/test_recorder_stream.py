"""
I9 / M9: live and recorded traces render over the same channel, and the
timeline continues updating after containment — this exercises the actual
SSE endpoint a browser would connect to, not just the broadcaster in
isolation.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import uvicorn

from common.schema import (
    AgentLifecyclePayload,
    ContainmentAction,
    ContainmentEventPayload,
    Session,
    SessionStatus,
    Step,
    StepType,
)
from recorder.main import create_app
from recorder.store.s3_archive import LocalDiskArchive


async def _run_server(app):
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    return server, task, f"http://127.0.0.1:{port}"


async def _read_sse_events(line_iter, count: int) -> list[dict]:
    """`line_iter` must be the SAME async iterator across calls — httpx
    does not allow re-entering aiter_lines() on a response whose raw
    stream has already been partially consumed."""
    events: list[dict] = []
    event_name = None
    async for line in line_iter:
        if line.startswith("event:"):
            event_name = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            data = line.removeprefix("data:").strip()
            events.append({"event": event_name, "data": json.loads(data)})
            if len(events) >= count:
                return events
    return events


@pytest.mark.asyncio
async def test_stream_replays_existing_steps_then_tails_new_ones(postgres_store, tmp_path):
    app = create_app(store=postgres_store, archive=LocalDiskArchive(tmp_path / "archive"), exporters=[])
    server, task, base_url = await _run_server(app)

    try:
        session = Session(
            agent_id="a", agent_version="0.1.0", human_id="user:jane", task_description="stream test",
        )
        async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as http:
            await http.post("/sessions", content=session.model_dump_json(), headers={"content-type": "application/json"})
            first_step = Step(
                session_id=session.session_id, sequence=0, type=StepType.agent_lifecycle,
                payload=AgentLifecyclePayload(event="started"),
            )
            await http.post(
                f"/sessions/{session.session_id}/steps", content=first_step.model_dump_json(),
                headers={"content-type": "application/json"},
            )
            await asyncio.sleep(0.3)  # let the drain loop land it before we connect

            async with http.stream("GET", f"/sessions/{session.session_id}/stream") as response:
                line_iter = response.aiter_lines()
                # first two SSE events: the session snapshot, then the one existing step
                initial = await _read_sse_events(line_iter, 2)
                assert initial[0]["event"] == "session"
                assert initial[1]["event"] == "step"
                assert initial[1]["data"]["type"] == "agent_lifecycle"

                # now publish a NEW step while the stream is open — this is
                # the "timeline continues updating" acceptance criterion
                second_step = Step(
                    session_id=session.session_id, sequence=1, type=StepType.containment_event,
                    payload=ContainmentEventPayload(
                        action=ContainmentAction.forwarding_stopped, initiated_by="user:soc",
                    ),
                )
                post_task = asyncio.create_task(
                    http.post(
                        f"/sessions/{session.session_id}/steps", content=second_step.model_dump_json(),
                        headers={"content-type": "application/json"},
                    )
                )
                live_events = await _read_sse_events(line_iter, 1)
                await post_task

                assert live_events[0]["event"] == "step"
                assert live_events[0]["data"]["type"] == "containment_event"
                assert live_events[0]["data"]["payload"]["action"] == "forwarding_stopped"
    finally:
        server.should_exit = True
        await task


@pytest.mark.asyncio
async def test_stream_closes_after_a_terminal_session_status(postgres_store, tmp_path):
    app = create_app(store=postgres_store, archive=LocalDiskArchive(tmp_path / "archive"), exporters=[])
    server, task, base_url = await _run_server(app)

    try:
        session = Session(
            agent_id="a", agent_version="0.1.0", human_id="user:jane", task_description="stream closes test",
            status=SessionStatus.completed,
        )
        async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as http:
            await http.post("/sessions", content=session.model_dump_json(), headers={"content-type": "application/json"})
            await asyncio.sleep(0.3)

            async with http.stream("GET", f"/sessions/{session.session_id}/stream") as response:
                line_iter = response.aiter_lines()
                events = await _read_sse_events(line_iter, 1)
                assert events[0]["event"] == "session"
                assert events[0]["data"]["status"] == "completed"
                # stream ends on its own — no more events, no hang
                remaining = [line async for line in line_iter]
                assert remaining == [] or all(not line.strip() for line in remaining)
    finally:
        server.should_exit = True
        await task
