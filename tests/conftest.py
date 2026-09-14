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
