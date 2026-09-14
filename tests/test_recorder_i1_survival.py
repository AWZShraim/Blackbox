"""
M5 acceptance, the headline one (I1): kill the agent container mid-run and
confirm the trace remains open, records the lifecycle event, and continues
accepting events. No Docker on this machine, so "container" here is a real
OS subprocess (scenarios/agent/run_scenario.py) that gets a genuine
SIGKILL — the mediator and recorder are separate live processes throughout
and never notice the agent died except by the silence.
"""

from __future__ import annotations

import asyncio
import signal
import sys
import uuid
from pathlib import Path

import pytest
import uvicorn

from mediator.core import Mediator
from mediator.credentials.local import LocalDevBroker
from mediator.emit import AsyncQueueEmitter
from mediator.execution.sandbox import InProcessSandbox
from mediator.ingress.session import SessionStore
from mediator.main import create_app as create_mediator_app
from mediator.policy.engine import PolicyEngine
from mediator.providers.base import ModelResponse, ToolCall
from recorder.client import RecorderHttpCollector
from recorder.main import create_app as create_recorder_app
from recorder.store.s3_archive import LocalDiskArchive
from scenarios.company.seed import seed
from scenarios.tools.definitions import build_registry

REPO_ROOT = Path(__file__).parent.parent


class SlowFakeProvider:
    """Returns the first scripted response immediately, then stalls
    (simulating a slow model call) before the second — the test kills the
    agent subprocess during that stall, after the first tool round trip has
    already landed in the recorder."""

    def __init__(self, script: list[ModelResponse], *, stall_before_call_index: int, stall_seconds: float) -> None:
        self._script = list(script)
        self._stall_before = stall_before_call_index
        self._stall_seconds = stall_seconds
        self.call_count = 0

    async def create_message(self, *, model, system, messages, tools, max_tokens=1024):
        if self.call_count == self._stall_before:
            await asyncio.sleep(self._stall_seconds)
        self.call_count += 1
        return self._script.pop(0)


async def _run_server(app) -> tuple[uvicorn.Server, asyncio.Task, str]:
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    return server, task, f"http://127.0.0.1:{port}"


@pytest.mark.asyncio
async def test_recorder_survives_the_agent_being_killed_mid_run(postgres_dsn, tmp_path):
    # --- recorder: its own live process (well, its own event loop; a real
    # deployment runs it as a genuinely separate OS process — Section 10
    # requires HTTP between mediator and recorder specifically so that
    # separation is real even locally, which this test exercises for real).
    from recorder.store.postgres import PostgresStore

    recorder_store = PostgresStore(postgres_dsn)
    recorder_app = create_recorder_app(
        store=recorder_store, archive=LocalDiskArchive(tmp_path / "archive"), exporters=[],
    )
    recorder_server, recorder_task, recorder_url = await _run_server(recorder_app)

    # --- mediator: wired to the recorder over real HTTP (I1, Section 10) ---
    db_path = tmp_path / "northwind_test.db"
    seed(db_path, n_customers=20, n_orders=40, n_tickets=39)

    script = [
        ModelResponse(stop_reason="tool_use", text=None, tool_calls=[ToolCall(id="c1", name="get_ticket", input={"id": 1})]),
        ModelResponse(stop_reason="end_turn", text="Resolved.", tool_calls=[]),
    ]
    provider = SlowFakeProvider(script, stall_before_call_index=1, stall_seconds=10.0)
    emitter = AsyncQueueEmitter(RecorderHttpCollector(recorder_url))
    mediator = Mediator(
        registry=build_registry(), policy=PolicyEngine.load(),
        credential_broker=LocalDevBroker(db_path=db_path), sandbox=InProcessSandbox(),
        collector=emitter, provider=provider,
    )
    sessions = SessionStore()
    sessions.register_client(
        client_id="test-agent", client_secret="test-secret", agent_id="support-agent", agent_version="0.1.0"
    )
    mediator_app = create_mediator_app(mediator=mediator, sessions=sessions)

    async def mediator_lifespan_wrapper():
        emitter.start()

    await mediator_lifespan_wrapper()
    mediator_server, mediator_task, mediator_url = await _run_server(mediator_app)

    try:
        # --- the agent: a REAL OS subprocess, killed for real ---
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "scenarios.agent.run_scenario",
            "--base-url", mediator_url, "--client-id", "test-agent", "--client-secret", "test-secret",
            "--human-id", "user:jane.doe", "--task", "Resolve ticket #1 for the customer.",
            cwd=str(REPO_ROOT), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )

        session_id: str | None = None
        assert proc.stdout is not None
        for _ in range(50):
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=5.0)
            if not line:
                break
            text = line.decode().strip()
            if text.startswith("SESSION "):
                session_id = text.split(" ", 1)[1]
                break
        assert session_id is not None, "agent subprocess never reported its session id"

        # Give the first tool round trip time to land in the recorder.
        first_tool_result_seen = False
        for _ in range(50):
            import httpx
            async with httpx.AsyncClient() as http:
                resp = await http.get(f"{recorder_url}/sessions/{session_id}")
            if resp.status_code == 200:
                steps = resp.json()["steps"]
                if any(s["type"] == "tool_result" for s in steps):
                    first_tool_result_seen = True
                    break
            await asyncio.sleep(0.1)
        assert first_tool_result_seen, "first tool call never made it to the recorder before kill"

        # --- kill the agent, hard, mid-run (it's stalled on the 2nd model call) ---
        proc.send_signal(signal.SIGKILL)
        await asyncio.wait_for(proc.wait(), timeout=5.0)
        assert proc.returncode != 0  # it died, it did not finish cleanly

        # --- the recorder must still be healthy, with zero drops ---
        import httpx
        async with httpx.AsyncClient() as http:
            health = await http.get(f"{recorder_url}/health")
        assert health.status_code == 200
        assert health.json()["drop_count"] == 0

        # --- the trace up to the kill is intact, and the session is NOT
        # auto-closed just because the agent process vanished ---
        async with httpx.AsyncClient() as http:
            trace_resp = await http.get(f"{recorder_url}/sessions/{session_id}")
        trace = trace_resp.json()
        assert trace["session"]["status"] == "running"
        step_types_before = [s["type"] for s in trace["steps"]]
        assert "tool_result" in step_types_before
        assert "agent_lifecycle" in step_types_before  # the "started" event

        # --- a watchdog (NOT the dead agent) detects the crash and records
        # it — this is the I1 assertion: recording survives the kill, and
        # keeps accepting new events for the same session afterward. The
        # watchdog is a trusted Blackbox-side actor, so it mints its own
        # token from the session store rather than needing the dead
        # agent's token. ---
        watchdog_token = sessions.issue_token(uuid.UUID(session_id))
        import httpx
        async with httpx.AsyncClient() as http:
            lifecycle_resp = await http.post(
                f"{mediator_url}/session/{session_id}/lifecycle",
                headers={"Authorization": f"Bearer {watchdog_token}"},
                json={"event": "terminated", "reason": "agent process killed (SIGKILL) mid-run", "initiated_by": "watchdog"},
            )
        assert lifecycle_resp.status_code == 200, lifecycle_resp.text

        # give the async pipeline (mediator queue -> HTTP -> recorder queue
        # -> postgres) a moment to land
        final_trace = None
        for _ in range(50):
            async with httpx.AsyncClient() as http:
                resp = await http.get(f"{recorder_url}/sessions/{session_id}")
            body = resp.json()
            has_terminated_step = any(
                s["type"] == "agent_lifecycle" and s["payload"]["event"] == "terminated"
                for s in body["steps"]
            )
            # both the step AND the session-status update travel through the
            # emitter independently (I2) — wait for both to have landed.
            if has_terminated_step and body["session"]["status"] == "terminated":
                final_trace = body
                break
            await asyncio.sleep(0.1)

        assert final_trace is not None, "terminated lifecycle event never reached the recorder"
        # everything recorded BEFORE the kill is still there — the trace
        # was never truncated or reset, only appended to (I1).
        final_step_types = [s["type"] for s in final_trace["steps"]]
        assert "tool_result" in final_step_types
        assert final_step_types.count("agent_lifecycle") == 2  # started, then terminated
        assert final_trace["session"]["status"] == "terminated"

        terminated_step = next(
            s for s in final_trace["steps"]
            if s["type"] == "agent_lifecycle" and s["payload"]["event"] == "terminated"
        )
        assert terminated_step["payload"]["initiated_by"] == "watchdog"

    finally:
        mediator_server.should_exit = True
        await mediator_task
        await emitter.stop(drain_remaining=False)
        recorder_server.should_exit = True
        await recorder_task
