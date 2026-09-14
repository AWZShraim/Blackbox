"""M5 acceptance: recorder health shows zero drops under normal load."""

from __future__ import annotations

import asyncio
import uuid

import httpx
import pytest
import uvicorn

from common.schema import AgentLifecyclePayload, Session, Step, StepType
from recorder.main import create_app
from recorder.store.s3_archive import LocalDiskArchive


@pytest.mark.asyncio
async def test_recorder_accepts_a_burst_of_events_with_zero_drops(postgres_dsn, tmp_path):
    from recorder.store.postgres import PostgresStore

    store = PostgresStore(postgres_dsn)
    app = create_app(store=store, archive=LocalDiskArchive(tmp_path / "archive"), exporters=[])
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    base_url = f"http://127.0.0.1:{port}"

    try:
        session = Session(
            agent_id="load-test-agent", agent_version="0.1.0", human_id="user:load-test",
            task_description="burst of steps under normal load",
        )
        async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as http:
            resp = await http.post("/sessions", content=session.model_dump_json(), headers={"content-type": "application/json"})
            assert resp.status_code == 202

            steps = [
                Step(
                    session_id=session.session_id, sequence=i, type=StepType.agent_lifecycle,
                    payload=AgentLifecyclePayload(event="started" if i == 0 else "completed", reason=f"load step {i}"),
                )
                for i in range(200)
            ]
            responses = await asyncio.gather(*[
                http.post(f"/sessions/{session.session_id}/steps", content=s.model_dump_json(), headers={"content-type": "application/json"})
                for s in steps
            ])
            assert all(r.status_code == 202 for r in responses)

            # let the drain loop catch up
            trace = None
            for _ in range(100):
                r = await http.get(f"/sessions/{session.session_id}")
                if r.status_code == 200 and len(r.json()["steps"]) == 200:
                    trace = r.json()
                    break
                await asyncio.sleep(0.05)
            assert trace is not None, "not all 200 steps landed in Postgres in time"

            health = (await http.get("/health")).json()
            assert health["drop_count"] == 0
            assert health["queue_depth"] == 0
    finally:
        server.should_exit = True
        await task
