"""
/mcp — MCP-compatible server endpoint (Section 6.1). Exposes the registered
tool catalogue over the real MCP Streamable HTTP transport, so any
MCP-speaking client (Claude Code, Cursor, Claude Desktop — Section 6.1, and
the M12 acceptance test) can be instrumented by pointing its MCP config at
this URL, no code changes. This is what makes the agentless roadmap real;
dropping it is a forbidden shortcut (Section 15).

Every tool call still goes through Mediator.handle_tool_call — policy,
credential minting, sandboxing, and recording are identical whether the
call arrived from the bespoke demo agent or from an external MCP client.
"""

from __future__ import annotations

import contextvars
import json
import uuid
from typing import Any

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from mediator.core import Mediator, SessionNotFound, ToolNotAllowed
from mediator.execution.registry import ToolRegistry
from mediator.ingress.session import SessionAuthError, SessionStore

# Set from the raw ASGI scope for each incoming HTTP request, read back
# inside the MCP tool-call handler that Server.call_tool() invokes within
# the same async task — this is how the Blackbox session token (carried as
# a normal Authorization: Bearer header on the MCP connection) reaches
# mediator.handle_tool_call without forking the MCP protocol itself.
_current_session_token: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "blackbox_mcp_session_token", default=None
)


def build_mcp_asgi_app(mediator: Mediator, sessions: SessionStore, registry: ToolRegistry):
    server: Server = Server("blackbox-mediator")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(name=t.name, description=t.description, inputSchema=t.input_schema)
            for t in registry.catalogue()
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
        token = _current_session_token.get()
        try:
            session_id = sessions.resolve(token)
        except SessionAuthError as exc:
            return [types.TextContent(type="text", text=f"error: {exc}")]

        tool_call_id = f"mcp-{uuid.uuid4().hex[:12]}"
        try:
            result = await mediator.handle_tool_call(
                session_id=session_id, tool_name=name, arguments=arguments, tool_call_id=tool_call_id,
            )
        except (ToolNotAllowed, SessionNotFound, RuntimeError) as exc:
            return [types.TextContent(type="text", text=json.dumps({"error": str(exc)}))]

        return [types.TextContent(type="text", text=json.dumps(result, default=str))]

    session_manager = StreamableHTTPSessionManager(app=server, json_response=True, stateless=True)

    async def asgi_app(scope, receive, send) -> None:
        if scope["type"] == "http":
            raw_headers = dict(scope.get("headers") or [])
            auth = raw_headers.get(b"authorization", b"").decode()
            token = auth.removeprefix("Bearer ").strip() if auth else None
            _current_session_token.set(token)
        await session_manager.handle_request(scope, receive, send)

    return asgi_app, session_manager
