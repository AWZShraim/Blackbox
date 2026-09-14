"""
The Northwind Support agent loop (Section 7): build messages, call the
model, parse tool calls, dispatch them, append results, loop.

Model-calling and tool-dispatch are injected via `AgentTransport` rather
than hardcoded, so this exact loop runs two ways without modification:
  - M3 (this milestone): DirectTransport (transport_direct.py) wires the
    loop straight to a ModelProvider and a ToolRegistry, to prove the loop
    and tool catalogue work before the mediator exists.
  - M4 onward: MediatedTransport (transport_mediated.py) speaks HTTP to the
    mediator's /v1/messages and /mcp endpoints. The agent then holds no
    credentials and every call is recorded (I3, I6) — the loop below is
    unaware of the difference.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from mediator.providers.base import ModelResponse

MAX_TURNS = 8

SYSTEM_PROMPT = (
    "You are a Northwind Support agent. Use the tools provided to resolve "
    "the customer's ticket efficiently. Keep any reply to the customer "
    "concise and professional."
)


class AgentTransport(Protocol):
    """Everything the loop needs from its environment. How each method is
    implemented — direct calls or HTTP through the mediator — is the only
    thing that changes between M3 and M4."""

    async def call_model(
        self, *, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ModelResponse: ...

    async def run_tool(self, name: str, arguments: dict[str, Any], *, tool_call_id: str) -> Any: ...


@dataclass
class AgentResult:
    final_text: str | None
    messages: list[dict[str, Any]]
    turns: int
    stop_reason: str


async def run_agent(
    transport: AgentTransport,
    *,
    task_description: str,
    tool_schemas: list[dict[str, Any]],
    system_prompt: str = SYSTEM_PROMPT,
    max_turns: int = MAX_TURNS,
) -> AgentResult:
    messages: list[dict[str, Any]] = [{"role": "user", "content": task_description}]

    for turn in range(max_turns):
        response = await transport.call_model(system=system_prompt, messages=messages, tools=tool_schemas)

        content_blocks: list[dict[str, Any]] = []
        if response.text:
            content_blocks.append({"type": "text", "text": response.text})
        for call in response.tool_calls:
            content_blocks.append({"type": "tool_use", "id": call.id, "name": call.name, "input": call.input})
        messages.append({"role": "assistant", "content": content_blocks})

        if response.stop_reason != "tool_use" or not response.tool_calls:
            return AgentResult(
                final_text=response.text, messages=messages, turns=turn + 1, stop_reason=response.stop_reason
            )

        tool_result_blocks: list[dict[str, Any]] = []
        for call in response.tool_calls:
            try:
                result = await transport.run_tool(call.name, call.input, tool_call_id=call.id)
                tool_result_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "content": json.dumps(result, default=str),
                })
            except Exception as exc:  # noqa: BLE001 - surfaced to the model, never swallowed
                tool_result_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "content": json.dumps({"error": str(exc)}),
                    "is_error": True,
                })
        messages.append({"role": "user", "content": tool_result_blocks})

    return AgentResult(final_text=None, messages=messages, turns=max_turns, stop_reason="max_turns_exceeded")
