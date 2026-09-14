"""
The mediator FastAPI app (Section 6.1). Two ingress protocols — POST
/v1/messages and /mcp — plus session establishment. Both ingress protocols
must exist in v1 (Section 6.1); the MCP endpoint is not optional.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from mediator.core import Mediator
from mediator.credentials.local import LocalDevBroker
from mediator.emit import AsyncQueueEmitter
from mediator.execution.sandbox import SubprocessSandbox
from mediator.ingress.mcp import build_mcp_asgi_app
from mediator.ingress.messages import build_messages_router
from mediator.ingress.session import SessionStore, build_session_router
from mediator.policy.engine import PolicyEngine
from mediator.providers import get_provider
from recorder.client import NullCollector, RecorderHttpCollector
from scenarios.tools.definitions import build_registry

load_dotenv()


def create_app(*, mediator: Mediator | None = None, sessions: SessionStore | None = None) -> FastAPI:
    """Both overrides exist for tests that need a FakeModelProvider, an
    InProcessSandbox (faster than real subprocess spawns), or an in-memory
    Collector to assert against — the production path (`app` below) always
    calls this with no arguments and gets the real, env-configured stack."""
    registry = build_registry()
    owns_emitter = mediator is None
    emitter: AsyncQueueEmitter | None = None

    if mediator is None:
        policy = PolicyEngine.load()
        credential_broker = LocalDevBroker()
        sandbox = SubprocessSandbox()

        recorder_url = os.environ.get("RECORDER_URL")
        sink = RecorderHttpCollector(recorder_url) if recorder_url else NullCollector()
        emitter = AsyncQueueEmitter(sink)

        try:
            provider = get_provider()
        except RuntimeError:
            provider = None  # no model key configured — tool-only calls still work

        mediator = Mediator(
            registry=registry, policy=policy, credential_broker=credential_broker,
            sandbox=sandbox, collector=emitter, provider=provider,
        )

    if sessions is None:
        sessions = SessionStore()
        sessions.register_client(
            client_id=os.environ.get("MEDIATOR_CLIENT_ID", "demo-agent"),
            client_secret=os.environ.get("MEDIATOR_CLIENT_SECRET", "demo-secret-change-me"),
            agent_id="support-agent",
            agent_version="0.1.0",
        )

    mcp_app, mcp_session_manager = build_mcp_asgi_app(mediator, sessions, registry)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if owns_emitter and emitter is not None:
            emitter.start()
        async with mcp_session_manager.run():
            yield
        if owns_emitter and emitter is not None:
            await emitter.stop()

    app = FastAPI(title="Blackbox Mediator", lifespan=lifespan)
    app.state.mediator = mediator
    app.state.sessions = sessions
    app.state.emitter = emitter

    app.include_router(build_session_router(mediator, sessions))
    app.include_router(build_messages_router(mediator, sessions))

    @app.get("/healthz")
    async def healthz():
        if emitter is None:
            return {"status": "ok", "queue_depth": None, "drop_count": None}
        return {"status": "ok", "queue_depth": emitter.queue_depth, "drop_count": emitter.drop_count}

    app.mount("/mcp", mcp_app)
    return app


app = create_app()
