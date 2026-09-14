"""
Session-scoped embedded Postgres (via `pgserver`, a real bundled postgres
binary — no Docker or system install needed) for recorder tests. Real
Postgres, not SQLite standing in for it — the spec is explicit that the hot
trace store is Postgres (Section 12), and swapping engines under test would
mean testing something else.
"""

from __future__ import annotations

import tempfile

import pytest
import pytest_asyncio


@pytest.fixture(scope="session")
def postgres_dsn():
    pgserver = pytest.importorskip("pgserver")
    tmpdir = tempfile.mkdtemp(prefix="blackbox-pgserver-")
    server = pgserver.get_server(tmpdir)
    uri = server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)
    yield uri
    server.cleanup()


@pytest_asyncio.fixture()
async def postgres_store(postgres_dsn):
    from recorder.store.postgres import PostgresStore

    store = PostgresStore(postgres_dsn)
    await store.create_tables()
    yield store
    await store.dispose()


@pytest.fixture(autouse=True)
def _reset_sse_starlette_app_status():
    """sse_starlette caches a module-level asyncio.Event the first time
    it's used, bound to whatever event loop was running then. pytest-asyncio
    gives each test function its own loop, so without this reset the
    second SSE test in a run fails with 'bound to a different event loop'
    — a known sse_starlette gotcha, not a bug in our streaming code."""
    from sse_starlette.sse import AppStatus

    AppStatus.should_exit_event = None
    yield
    AppStatus.should_exit_event = None
