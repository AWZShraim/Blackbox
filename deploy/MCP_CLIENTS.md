# Connecting an external MCP client (M12)

The mediator's `/mcp` endpoint (`mediator/ingress/mcp.py`) is the real MCP
Streamable HTTP transport, built on the official `mcp` Python SDK's
`StreamableHTTPSessionManager` — not a custom stand-in protocol. Any
MCP-speaking client can point at it by changing one config entry, exactly
as Section 6.1 requires.

## What's already verified

Every automated test that exercises `/mcp` (`tests/test_mediator_e2e.py`,
`tests/test_containment_http.py`'s live counterpart, and every live demo
run in M8-M10) uses the official `mcp` Python SDK's own
`streamablehttp_client` + `ClientSession` — the same client machinery
Claude Code, Cursor, and Claude Desktop use internally for HTTP MCP
servers. That is "another MCP client," not a mock, and it is what
`scenarios/agent/transport_mediated.py`'s `MediatedTransport` — the actual
demo agent used throughout M8-M10 — runs on every single live scenario.

Beyond the SDK client, the endpoint was also driven with plain `curl` —
raw MCP JSON-RPC 2.0 over HTTP, no SDK on either side — against a locally
running mediator: `initialize`, then `tools/list` (returned the real
10-tool catalogue with JSON schemas), then `tools/call` for `get_ticket`.
The call showed up in the recorder as a full
`tool_request`/`policy_decision`/`tool_result` step sequence, fetched back
via `GET /sessions/<id>` — confirming the endpoint is genuinely
protocol-compliant HTTP+JSON-RPC, not dependent on any particular client
library's quirks. One thing worth knowing if you try this yourself: the
mediator mounts `/mcp` as a sub-application, so a bare HTTP client (curl
without `-L`) needs to follow the `307` redirect to `/mcp/` (trailing
slash) — real MCP client libraries do this automatically.

The mediator's published p99 policy+baseline latency (Section 6.2's
budget) is in the root README and `scripts/measure_latency.py`.

## Connecting Claude Code, Cursor, or Claude Desktop

1. Establish a session first (the MCP endpoint needs a bearer token —
   Section 6.1's "a call without a valid session is rejected and
   logged"):

   ```bash
   curl -X POST http://localhost:8000/session/establish \
     -H "content-type: application/json" \
     -d '{
       "client_id": "demo-agent",
       "client_secret": "demo-secret-change-me",
       "human_id": "user:you",
       "task_description": "manual MCP client test"
     }'
   # -> {"session_token": "...", "session_id": "..."}
   ```

2. Add the mediator as an MCP server, with that token as a bearer header.
   For Claude Code (`.mcp.json` or `claude mcp add`):

   ```json
   {
     "mcpServers": {
       "blackbox": {
         "type": "http",
         "url": "http://localhost:8000/mcp",
         "headers": { "Authorization": "Bearer <session_token>" }
       }
     }
   }
   ```

   Cursor and Claude Desktop take the same three fields (URL + bearer
   header) in their own MCP config formats.

3. The client's `tools/list` call returns the full Northwind catalogue
   (`get_ticket`, `search_docs`, `issue_refund`, ...) with real JSON
   schemas — no raw-execution tools, since the registry refuses to
   register those at load time (I4). Every `tools/call` the client makes
   goes through the exact same `Mediator.handle_tool_call` path as the
   bespoke demo agent: policy evaluation, credential minting, sandboxed
   execution, and a recorded `tool_request`/`policy_decision`/
   `tool_result` step sequence — open the session in the Investigator
   (`http://localhost:3000/sessions/<session_id>`) and the client's calls
   appear exactly like an agent run would, live, while the client is still
   connected.

One session token is scoped to one session — start a fresh
`/session/establish` call (and a fresh `human_id`/`task_description`) for
each client you want to see as a separate, attributable trace.
