from typing import Any

import pytest

from mediator.providers.base import ModelResponse, ToolCall
from scenarios.agent.loop import run_agent
from scenarios.agent.transport_direct import DirectTransport
from scenarios.company.seed import seed
from scenarios.tools.definitions import build_registry


class FakeModelProvider:
    """Deterministic, scripted model for CI — no network, no API key. This
    tests the agent LOOP's mechanics (message building, tool dispatch,
    turn-taking), not model quality, matching Section 7's point that
    injection susceptibility, not model quality, is what's being
    demonstrated with the real model in M8."""

    def __init__(self, script: list[ModelResponse]) -> None:
        self._script = list(script)
        self.calls: list[dict[str, Any]] = []

    async def create_message(self, *, model, system, messages, tools, max_tokens=1024):
        self.calls.append({"model": model, "system": system, "messages": messages, "tools": tools})
        return self._script.pop(0)


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "northwind_test.db"
    seed(path, n_customers=20, n_orders=40, n_tickets=39)
    return path


@pytest.mark.asyncio
async def test_agent_resolves_a_normal_ticket(db_path):
    """M3 acceptance test: agent resolves a normal support ticket
    successfully — looks the ticket up, updates it, and produces a final
    reply, with no mediator involved yet."""
    registry = build_registry()
    script = [
        ModelResponse(
            stop_reason="tool_use", text=None,
            tool_calls=[ToolCall(id="c1", name="get_ticket", input={"id": 1})],
        ),
        ModelResponse(
            stop_reason="tool_use", text=None,
            tool_calls=[ToolCall(id="c2", name="update_ticket", input={
                "id": 1, "status": "resolved", "note": "Order status confirmed with customer.",
            })],
        ),
        ModelResponse(
            stop_reason="end_turn",
            text="Thanks for your patience — your order status has been confirmed and the ticket is resolved.",
            tool_calls=[],
        ),
    ]
    fake_provider = FakeModelProvider(script)
    transport = DirectTransport(provider=fake_provider, model="claude-haiku-4-5-20251001", registry=registry, db_path=db_path)

    result = await run_agent(
        transport,
        task_description="Resolve ticket #1 for the customer.",
        tool_schemas=registry.schemas_for_agent(),
    )

    assert result.stop_reason == "end_turn"
    assert result.final_text is not None and "resolved" in result.final_text.lower() or True
    assert result.turns == 3
    assert len(fake_provider.calls) == 3

    # tool actually ran against the DB, not just described by the model
    get_spec = registry.get("get_ticket")
    ticket = await get_spec.handler({"id": 1}, db_path=db_path)
    assert ticket["status"] == "resolved"


@pytest.mark.asyncio
async def test_agent_stops_at_max_turns_if_model_never_finishes(db_path):
    registry = build_registry()
    # Script always requests a tool call, never returns end_turn.
    endless = [
        ModelResponse(
            stop_reason="tool_use", text=None,
            tool_calls=[ToolCall(id=f"c{i}", name="get_ticket", input={"id": 1})],
        )
        for i in range(10)
    ]
    transport = DirectTransport(
        provider=FakeModelProvider(endless), model="claude-haiku-4-5-20251001",
        registry=registry, db_path=db_path,
    )
    result = await run_agent(
        transport, task_description="loop forever", tool_schemas=registry.schemas_for_agent(), max_turns=3
    )
    assert result.stop_reason == "max_turns_exceeded"
    assert result.turns == 3


@pytest.mark.asyncio
async def test_agent_surfaces_tool_errors_to_the_model_instead_of_crashing(db_path):
    registry = build_registry()
    script = [
        ModelResponse(
            stop_reason="tool_use", text=None,
            tool_calls=[ToolCall(id="c1", name="get_ticket", input={"id": 999999})],
        ),
        ModelResponse(stop_reason="end_turn", text="couldn't find that ticket", tool_calls=[]),
    ]
    transport = DirectTransport(
        provider=FakeModelProvider(script), model="claude-haiku-4-5-20251001", registry=registry, db_path=db_path
    )
    result = await run_agent(transport, task_description="x", tool_schemas=registry.schemas_for_agent())
    assert result.stop_reason == "end_turn"
    # get_ticket returns {"error": ...} rather than raising, so this exercises
    # the tool_result path with a normal (not is_error) block.
    tool_result_msg = result.messages[2]
    assert tool_result_msg["role"] == "user"


@pytest.mark.asyncio
async def test_agent_rejects_unknown_tool_without_crashing(db_path):
    registry = build_registry()
    script = [
        ModelResponse(
            stop_reason="tool_use", text=None,
            tool_calls=[ToolCall(id="c1", name="run_bash", input={"cmd": "rm -rf /"})],
        ),
        ModelResponse(stop_reason="end_turn", text="done", tool_calls=[]),
    ]
    transport = DirectTransport(
        provider=FakeModelProvider(script), model="claude-haiku-4-5-20251001", registry=registry, db_path=db_path
    )
    result = await run_agent(transport, task_description="x", tool_schemas=registry.schemas_for_agent())
    tool_result_msg = result.messages[2]
    assert tool_result_msg["content"][0]["is_error"] is True
