"""
M4 acceptance test, end to end: the M3 task completes through the mediator
over real HTTP and the real MCP protocol; every call produces steps; and
the agent-side transport object holds no credentials, verified by
inspecting its attributes rather than trusting a comment.
"""

from __future__ import annotations

import asyncio

import pytest
import uvicorn

from mediator.core import Mediator
from mediator.credentials.local import LocalDevBroker
from mediator.execution.sandbox import InProcessSandbox
from mediator.ingress.session import SessionStore
from mediator.main import create_app
from mediator.policy.engine import PolicyEngine
from mediator.providers.base import ModelResponse, ToolCall
from scenarios.agent.loop import run_agent
from scenarios.agent.transport_mediated import MediatedTransport, establish_session
from scenarios.company.seed import seed
from scenarios.tools.definitions import build_registry
from tests.fakes import InMemoryCollector


class FakeProvider:
    def __init__(self, script):
        self._script = list(script)

    async def create_message(self, *, model, system, messages, tools, max_tokens=1024):
        return self._script.pop(0)


@pytest.fixture()
async def live_server(tmp_path):
    db_path = tmp_path / "northwind_test.db"
    seed(db_path, n_customers=20, n_orders=40, n_tickets=39)

    collector = InMemoryCollector()
    script = [
        ModelResponse(stop_reason="tool_use", text=None, tool_calls=[ToolCall(id="c1", name="get_ticket", input={"id": 1})]),
        ModelResponse(
            stop_reason="tool_use", text=None,
            tool_calls=[ToolCall(id="c2", name="update_ticket", input={"id": 1, "status": "resolved", "note": "done"})],
        ),
        ModelResponse(stop_reason="end_turn", text="Your ticket has been resolved.", tool_calls=[]),
    ]
    mediator = Mediator(
        registry=build_registry(), policy=PolicyEngine.load(),
        credential_broker=LocalDevBroker(db_path=db_path), sandbox=InProcessSandbox(),
        collector=collector, provider=FakeProvider(script),
    )
    sessions = SessionStore()
    sessions.register_client(
        client_id="test-agent", client_secret="test-secret", agent_id="support-agent", agent_version="0.1.0"
    )

    app = create_app(mediator=mediator, sessions=sessions)
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]

    yield f"http://127.0.0.1:{port}", collector

    server.should_exit = True
    await task


@pytest.mark.asyncio
async def test_agent_resolves_a_ticket_entirely_through_the_mediator(live_server):
    base_url, collector = live_server

    session_token, session_id = await establish_session(
        base_url=base_url, client_id="test-agent", client_secret="test-secret",
        human_id="user:jane.doe", task_description="Resolve ticket #1",
    )

    async with MediatedTransport(base_url=base_url, session_token=session_token, model="claude-haiku-4-5-20251001") as transport:
        # M4 acceptance: "agent process holds no credentials (verify by
        # inspecting its environment)" — here, its environment IS this
        # object's attributes, since it never touches os.environ for
        # secrets. No attribute name may plausibly hold one.
        forbidden_substrings = ("api_key", "secret", "credential", "password", "db_path", "access_key")
        for attr_name in vars(transport):
            lowered = attr_name.lower()
            assert not any(s in lowered for s in forbidden_substrings), (
                f"MediatedTransport.{attr_name} looks like it might hold a credential (I3)"
            )

        registry_schemas = build_registry().schemas_for_agent()
        result = await run_agent(
            transport, task_description="Resolve ticket #1 for the customer.", tool_schemas=registry_schemas,
        )

    assert result.stop_reason == "end_turn"
    assert result.turns == 3

    # every call produced steps (M4 acceptance)
    step_types = [s.type.value for s in collector.steps]
    assert step_types.count("model_call") == 3
    assert step_types.count("model_response") == 3
    assert step_types.count("tool_request") == 2
    assert step_types.count("tool_result") == 2
    assert step_types.count("policy_decision") == 2
    assert all(s.session_id == collector.sessions[0].session_id for s in collector.steps)

    # Regression: provenance content_id must stay stable across the real
    # MCP round trip. The model's own tool_use.id has to reach the
    # mediator's provenance_by_call_id so a tool_result reappearing in a
    # LATER model_call's context_composition is recognized as the same
    # content, not re-minted with a random id every time (which would
    # silently break content_id-based backward tracing, I8).
    tool_result_step = next(s for s in collector.steps if s.type.value == "tool_result")
    original_content_id = tool_result_step.payload.provenance.content_id

    later_model_call = collector.steps[
        [s.type.value for s in collector.steps].index("model_call", collector.steps.index(tool_result_step) + 1)
    ]
    matching_segments = [
        seg for seg in later_model_call.payload.context_composition
        if seg.provenance.content_id == original_content_id
    ]
    assert matching_segments, (
        "the tool_result's content_id never reappeared in the next model_call's "
        "context_composition — provenance tracking is broken on the MCP path"
    )
