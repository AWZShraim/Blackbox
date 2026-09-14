"""
M4 onward: wires the agent loop to the mediator over the wire — HTTP for
/v1/messages, the real MCP protocol for tool calls. This object holds
exactly two things: the mediator's base URL and a session token. No model
API key, no database path, no cloud credential (I3) — that is the entire
point of this file existing, and M4's acceptance test asserts it by
inspecting the object's attributes rather than trusting a comment.

loop.py does not change between transport_direct.py (M3) and this file.
"""

from __future__ import annotations

import json
from contextlib import AsyncExitStack
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from mediator.ingress.mcp import TOOL_CALL_ID_ARG_KEY
from mediator.providers.base import ModelResponse, ToolCall


class MediatedTransport:
    """Holds only `base_url` and `session_token` — no credentials of any
    kind. Every field is deliberately public so a test can assert this by
    enumerating `vars(transport)` rather than trusting a docstring."""

    def __init__(self, *, base_url: str, session_token: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session_token = session_token
        self.model = model
        self._http = httpx.AsyncClient(
            base_url=self.base_url, headers={"Authorization": f"Bearer {session_token}"}, timeout=30.0
        )
        self._mcp_stack: AsyncExitStack | None = None
        self._mcp_session: ClientSession | None = None

    async def __aenter__(self) -> "MediatedTransport":
        self._mcp_stack = AsyncExitStack()
        read, write, _ = await self._mcp_stack.enter_async_context(
            streamablehttp_client(f"{self.base_url}/mcp", headers={"Authorization": f"Bearer {self.session_token}"})
        )
        self._mcp_session = await self._mcp_stack.enter_async_context(ClientSession(read, write))
        await self._mcp_session.initialize()
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        if self._mcp_stack is not None:
            await self._mcp_stack.aclose()
        await self._http.aclose()

    async def call_model(
        self, *, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ModelResponse:
        resp = await self._http.post(
            "/v1/messages",
            json={"model": self.model, "system": system, "messages": messages, "tools": tools, "max_tokens": 1024},
        )
        resp.raise_for_status()
        body = resp.json()
        tool_calls = [
            ToolCall(id=b["id"], name=b["name"], input=b["input"])
            for b in body["content"] if b["type"] == "tool_use"
        ]
        text = next((b["text"] for b in body["content"] if b["type"] == "text"), None)
        usage = body.get("usage", {})
        return ModelResponse(
            stop_reason=body["stop_reason"], text=text, tool_calls=tool_calls,
            input_tokens=usage.get("input_tokens", 0), output_tokens=usage.get("output_tokens", 0),
        )

    async def run_tool(self, name: str, arguments: dict[str, Any], *, tool_call_id: str) -> Any:
        if self._mcp_session is None:
            raise RuntimeError("MediatedTransport must be used as `async with MediatedTransport(...) as t:`")
        # Carries the model's own tool_use.id through to the mediator so
        # provenance_by_call_id (mediator/core.py) is keyed by the same id
        # loop.py will use as tool_use_id when it builds the tool_result
        # block for the NEXT model call — without this, the mediator can't
        # tell which provenance record a reappearing tool_result belongs
        # to, and content_id-based backward tracing (I8) silently breaks.
        wire_arguments = {**arguments, TOOL_CALL_ID_ARG_KEY: tool_call_id}
        result = await self._mcp_session.call_tool(name, wire_arguments)
        text = "".join(block.text for block in result.content if block.type == "text")
        payload = json.loads(text) if text else None
        if result.isError or (isinstance(payload, dict) and "error" in payload):
            raise RuntimeError(payload.get("error") if isinstance(payload, dict) else text)
        return payload


async def establish_session(
    *, base_url: str, client_id: str, client_secret: str, human_id: str, task_description: str, **human_context: Any
) -> tuple[str, str]:
    """Returns (session_token, session_id). A thin wrapper, not part of
    AgentTransport — session establishment happens once, before the loop."""
    async with httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=10.0) as http:
        resp = await http.post(
            "/session/establish",
            json={
                "client_id": client_id, "client_secret": client_secret,
                "human_id": human_id, "task_description": task_description, **human_context,
            },
        )
        resp.raise_for_status()
        body = resp.json()
        return body["session_token"], body["session_id"]


async def record_lifecycle_event(
    *, base_url: str, session_token: str, session_id: str, event: str,
    reason: str | None = None, initiated_by: str | None = None,
) -> None:
    """Used both by the agent itself (started/completed/failed) and,
    independently, by anything watching the agent's process from the
    outside (terminated, after a crash) — I1 depends on this being callable
    by a party other than the agent."""
    async with httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=10.0) as http:
        resp = await http.post(
            f"/session/{session_id}/lifecycle",
            headers={"Authorization": f"Bearer {session_token}"},
            json={"event": event, "reason": reason, "initiated_by": initiated_by},
        )
        resp.raise_for_status()
