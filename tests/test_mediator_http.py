import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mediator.core import Mediator
from mediator.credentials.local import LocalDevBroker
from mediator.execution.sandbox import InProcessSandbox
from mediator.ingress.messages import build_messages_router
from mediator.ingress.session import SessionStore, build_session_router
from mediator.policy.engine import PolicyEngine
from mediator.providers.base import ModelResponse
from scenarios.company.seed import seed
from scenarios.tools.definitions import build_registry
from tests.fakes import InMemoryCollector


class FakeProvider:
    def __init__(self, script):
        self._script = list(script)

    async def create_message(self, *, model, system, messages, tools, max_tokens=1024):
        return self._script.pop(0)


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "northwind_test.db"
    seed(path, n_customers=20, n_orders=40, n_tickets=39)
    return path


def build_test_app(*, provider=None, db_path=None):
    mediator = Mediator(
        registry=build_registry(), policy=PolicyEngine.load(),
        credential_broker=LocalDevBroker(db_path=db_path), sandbox=InProcessSandbox(),
        collector=(collector := InMemoryCollector()), provider=provider,
    )
    sessions = SessionStore()
    sessions.register_client(
        client_id="test-agent", client_secret="test-secret", agent_id="support-agent", agent_version="0.1.0"
    )
    app = FastAPI()
    app.include_router(build_session_router(mediator, sessions))
    app.include_router(build_messages_router(mediator, sessions))
    return app, mediator, collector


def _establish(client) -> str:
    resp = client.post("/session/establish", json={
        "client_id": "test-agent", "client_secret": "test-secret",
        "human_id": "user:jane.doe", "task_description": "resolve ticket 1",
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["session_token"]


def test_session_establish_rejects_bad_credentials(db_path):
    app, mediator, collector = build_test_app(db_path=db_path)
    client = TestClient(app)
    resp = client.post("/session/establish", json={
        "client_id": "test-agent", "client_secret": "WRONG", "human_id": "user:jane", "task_description": "x",
    })
    assert resp.status_code == 401


def test_session_establish_binds_agent_and_human_identity(db_path):
    app, mediator, collector = build_test_app(db_path=db_path)
    client = TestClient(app)
    token = _establish(client)
    assert token
    assert len(collector.sessions) == 1
    assert collector.sessions[0].human_id == "user:jane.doe"  # I7


def test_v1_messages_rejects_missing_session_token(db_path):
    app, mediator, collector = build_test_app(db_path=db_path)
    client = TestClient(app)
    resp = client.post("/v1/messages", json={
        "model": "claude-haiku-4-5-20251001", "messages": [{"role": "user", "content": "hi"}],
    })
    assert resp.status_code == 401


def test_v1_messages_proxies_to_the_model_and_records_both_directions(db_path):
    script = [ModelResponse(stop_reason="end_turn", text="hello", tool_calls=[])]
    app, mediator, collector = build_test_app(provider=FakeProvider(script), db_path=db_path)
    client = TestClient(app)
    token = _establish(client)

    resp = client.post(
        "/v1/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"model": "claude-haiku-4-5-20251001", "system": "sys", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["stop_reason"] == "end_turn"

    step_types = [s.type.value for s in collector.steps]
    assert "model_call" in step_types  # what the agent sent (I6: the "why")
    assert "model_response" in step_types  # what the model said back
