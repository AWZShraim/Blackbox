"""
Measures the mediator's policy + baseline evaluation overhead (Section
6.2's <10ms p99 budget, excluding actual tool execution) and prints the
result — this is what the README's published p99 number comes from.

Usage: python -m scripts.measure_latency [n_calls]
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

from detector.baseline import ArgumentShape, Baseline, ToolBaseline
from mediator.core import Mediator
from mediator.credentials.local import LocalDevBroker
from mediator.execution.sandbox import InProcessSandbox
from mediator.policy.engine import PolicyEngine
from scenarios.company.seed import seed
from scenarios.tools.definitions import build_registry
from tests.fakes import InMemoryCollector


async def main() -> None:
    n_calls = int(sys.argv[1]) if len(sys.argv) > 1 else 2000

    tmpdir = Path(tempfile.mkdtemp())
    db_path = tmpdir / "northwind_bench.db"
    seed(db_path, n_customers=20, n_orders=40, n_tickets=39)

    # A populated baseline so the inline check does real work (an empty
    # baseline would make this an unrealistically cheap no-op measurement).
    baseline = Baseline(
        subject_type="agent", subject_id="bench-agent", learned_at="2026-01-01T00:00:00Z",
        sessions_observed=100, tool_set=["get_ticket", "update_ticket"],
        tools={
            "get_ticket": ToolBaseline(call_count=100, argument_shapes={"id": ArgumentShape(is_numeric=True, min_value=1.0, max_value=200.0)}),
            "update_ticket": ToolBaseline(call_count=100, argument_shapes={"id": ArgumentShape(is_numeric=True, min_value=1.0, max_value=200.0)}),
        },
        sequences=[["get_ticket", "update_ticket"]],
    )

    mediator = Mediator(
        registry=build_registry(), policy=PolicyEngine.load(),
        credential_broker=LocalDevBroker(db_path=db_path), sandbox=InProcessSandbox(),
        collector=InMemoryCollector(), agent_baseline=baseline,
    )
    session = await mediator.create_session(
        agent_id="bench-agent", agent_version="0.1.0", human_id="user:bench", task_description="latency bench",
    )

    for i in range(n_calls):
        await mediator.handle_tool_call(
            session_id=session.session_id, tool_name="get_ticket", arguments={"id": (i % 20) + 1},
            tool_call_id=f"c{i}",
        )

    latency = mediator.policy_baseline_latency
    print(f"samples={latency.count}")
    print(f"p50={latency.p50:.4f}ms")
    print(f"p99={latency.p99:.4f}ms")
    print(f"under 10ms budget: {latency.p99 < 10.0}")


if __name__ == "__main__":
    asyncio.run(main())
