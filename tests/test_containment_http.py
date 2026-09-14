"""
M9 acceptance: contain mid-run via the real HTTP containment endpoint;
subsequent calls are refused; trace shows post_containment: true events;
credentials are actually revoked, not just marked so in the session
status.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mediator.core import Mediator
from mediator.credentials.local import LocalDevBroker
from mediator.execution.sandbox import InProcessSandbox
from mediator.ingress.containment import build_containment_router
from mediator.ingress.session import SessionStore, build_session_router
from mediator.policy.engine import PolicyEngine
from scenarios.company.seed import seed
from scenarios.tools.definitions import build_registry
from tests.fakes import InMemoryCollector


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "northwind_test.db"
    seed(path, n_customers=20, n_orders=40, n_tickets=39)
    return path


def build_test_app(*, db_path):
    broker = LocalDevBroker(db_path=db_path)
    mediator = Mediator(
        registry=build_registry(), policy=PolicyEngine.load(), credential_broker=broker,
        sandbox=InProcessSandbox(), collector=(collector := InMemoryCollector()),
    )
    sessions = SessionStore()
    sessions.register_client(
        client_id="test-agent", client_secret="test-secret", agent_id="support-agent", agent_version="0.1.0"
    )
    app = FastAPI()
    app.include_router(build_session_router(mediator, sessions))
    app.include_router(build_containment_router(mediator))
    return app, mediator, collector, broker


def test_contain_requires_the_operator_key(db_path, monkeypatch):
    monkeypatch.setenv("BLACKBOX_OPERATOR_KEY", "correct-key")
    app, mediator, collector, broker = build_test_app(db_path=db_path)
    client = TestClient(app)
    resp = client.post(
        "/session/establish",
        json={"client_id": "test-agent", "client_secret": "test-secret", "human_id": "user:jane", "task_description": "x"},
    )
    session_id = resp.json()["session_id"]

    denied = client.post(f"/sessions/{session_id}/contain", json={"initiated_by": "user:soc"})
    assert denied.status_code == 401

    wrong_key = client.post(
        f"/sessions/{session_id}/contain", json={"initiated_by": "user:soc"},
        headers={"X-Blackbox-Operator-Key": "wrong"},
    )
    assert wrong_key.status_code == 401

    ok = client.post(
        f"/sessions/{session_id}/contain", json={"initiated_by": "user:soc"},
        headers={"X-Blackbox-Operator-Key": "correct-key"},
    )
    assert ok.status_code == 200


@pytest.mark.asyncio
async def test_contain_mid_run_refuses_subsequent_calls_and_revokes_credentials(db_path, monkeypatch):
    monkeypatch.setenv("BLACKBOX_OPERATOR_KEY", "correct-key")
    app, mediator, collector, broker = build_test_app(db_path=db_path)
    client = TestClient(app)

    resp = client.post(
        "/session/establish",
        json={"client_id": "test-agent", "client_secret": "test-secret", "human_id": "user:jane", "task_description": "x"},
    )
    session_id = resp.json()["session_id"]
    session_uuid = uuid.UUID(session_id)

    # a call before containment succeeds and mints a credential
    result = await mediator.handle_tool_call(
        session_id=session_uuid, tool_name="get_ticket", arguments={"id": 1}, tool_call_id="c1",
    )
    assert result["id"] == 1
    outstanding_before = [ref for ref in broker._outstanding]  # noqa: SLF001 - test-only introspection
    assert outstanding_before == []  # already revoked right after use (Section 6.2 step 7), as expected

    contain_resp = client.post(
        f"/sessions/{session_id}/contain", json={"initiated_by": "user:soc", "reason": "suspected compromise"},
        headers={"X-Blackbox-Operator-Key": "correct-key"},
    )
    assert contain_resp.status_code == 200

    status_resp = client.get(f"/sessions/{session_id}/status")
    assert status_resp.json()["status"] == "contained"

    # subsequent call is refused
    from mediator.core import ToolNotAllowed

    with pytest.raises(ToolNotAllowed):
        await mediator.handle_tool_call(
            session_id=session_uuid, tool_name="get_ticket", arguments={"id": 2}, tool_call_id="c2",
        )

    step_types_post = [s.type.value for s in collector.steps if s.post_containment]
    assert "containment_event" not in [
        s.type.value for s in collector.steps if s.post_containment
    ]  # the containment_event itself is not post_containment, it IS the containment
    assert "tool_request" in step_types_post
    assert "policy_decision" in step_types_post
    assert "tool_result" in step_types_post

    refused_result = next(
        s for s in collector.steps if s.post_containment and s.type.value == "tool_result"
    )
    assert refused_result.payload.success is False

    containment_events = [s for s in collector.steps if s.type.value == "containment_event"]
    assert {e.payload.action.value for e in containment_events} == {"forwarding_stopped", "credentials_revoked"}
    assert all(e.payload.initiated_by == "user:soc" for e in containment_events)
