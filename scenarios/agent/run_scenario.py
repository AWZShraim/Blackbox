"""
Runs one agent task end to end against a live mediator, entirely over
HTTP/MCP (MediatedTransport). This is a real, standalone entry point —
`make scenario SCENARIO=...` runs it in local dev (Section 10), and
tests/test_recorder_i1_survival.py launches it as a genuine OS subprocess
and SIGKILLs it mid-run, to prove I1 without needing Docker to do it.
"""

from __future__ import annotations

import argparse
import asyncio
import os

from scenarios.agent.loop import run_agent
from scenarios.agent.transport_mediated import MediatedTransport, establish_session, record_lifecycle_event
from scenarios.tools.definitions import build_registry


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("MEDIATOR_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--client-id", default=os.environ.get("MEDIATOR_CLIENT_ID", "demo-agent"))
    parser.add_argument("--client-secret", default=os.environ.get("MEDIATOR_CLIENT_SECRET", "demo-secret-change-me"))
    parser.add_argument("--human-id", default="user:demo")
    parser.add_argument("--task", default="Resolve ticket #1 for the customer.")
    parser.add_argument("--model", default="claude-haiku-4-5-20251001")
    parser.add_argument("--scenario-id", default=None)
    args = parser.parse_args()

    session_token, session_id = await establish_session(
        base_url=args.base_url, client_id=args.client_id, client_secret=args.client_secret,
        human_id=args.human_id, task_description=args.task, scenario_id=args.scenario_id,
    )
    # Flushed immediately so a test harness can read the session_id off
    # stdout before this process potentially gets killed.
    print(f"SESSION {session_id}", flush=True)

    await record_lifecycle_event(
        base_url=args.base_url, session_token=session_token, session_id=session_id,
        event="started", initiated_by=args.human_id,
    )

    registry = build_registry()
    stop_reason = "unknown"
    try:
        async with MediatedTransport(base_url=args.base_url, session_token=session_token, model=args.model) as transport:
            result = await run_agent(transport, task_description=args.task, tool_schemas=registry.schemas_for_agent())
        stop_reason = result.stop_reason
        await record_lifecycle_event(
            base_url=args.base_url, session_token=session_token, session_id=session_id, event="completed",
        )
    except Exception as exc:  # noqa: BLE001 - reported, then re-raised
        await record_lifecycle_event(
            base_url=args.base_url, session_token=session_token, session_id=session_id,
            event="failed", reason=str(exc),
        )
        raise
    finally:
        print(f"DONE stop_reason={stop_reason}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
