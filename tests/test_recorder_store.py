import json
from pathlib import Path

import pytest

from common.schema import Trace


@pytest.fixture()
def fixture_trace() -> Trace:
    fixture_path = Path(__file__).parent.parent / "scenarios" / "fixtures" / "clean_session.json"
    return Trace.model_validate(json.loads(fixture_path.read_text()))


@pytest.mark.asyncio
async def test_full_clean_trace_is_stored_and_retrievable(postgres_store, fixture_trace):
    """M5 acceptance: a full clean trace is stored and retrievable."""
    await postgres_store.upsert_session(fixture_trace.session)
    for step in fixture_trace.steps:
        await postgres_store.insert_step(step)

    round_tripped = await postgres_store.get_trace(fixture_trace.session.session_id)
    assert round_tripped is not None
    assert round_tripped.session.human_id == fixture_trace.session.human_id
    assert len(round_tripped.steps) == len(fixture_trace.steps)
    assert [s.sequence for s in round_tripped.steps] == sorted(s.sequence for s in fixture_trace.steps)

    tool_result = next(s for s in round_tripped.steps if s.type.value == "tool_result")
    assert tool_result.payload.provenance.source_identifier == "ticket:4471"


@pytest.mark.asyncio
async def test_get_trace_returns_none_for_unknown_session(postgres_store):
    import uuid
    assert await postgres_store.get_trace(uuid.uuid4()) is None


@pytest.mark.asyncio
async def test_upsert_session_updates_status_in_place(postgres_store, fixture_trace):
    from common.schema import SessionStatus

    await postgres_store.upsert_session(fixture_trace.session)
    updated = fixture_trace.session.model_copy(update={"status": SessionStatus.contained})
    await postgres_store.upsert_session(updated)

    fetched = await postgres_store.get_session(fixture_trace.session.session_id)
    assert fetched.status.value == "contained"


@pytest.mark.asyncio
async def test_list_sessions_filters_by_human_id(postgres_store, fixture_trace):
    await postgres_store.upsert_session(fixture_trace.session)
    matches = await postgres_store.list_sessions(human_id=fixture_trace.session.human_id)
    assert any(s.session_id == fixture_trace.session.session_id for s in matches)

    no_matches = await postgres_store.list_sessions(human_id="user:nobody")
    assert no_matches == []


@pytest.mark.asyncio
async def test_search_steps_by_content_identifier_finds_the_ticket(postgres_store, fixture_trace):
    await postgres_store.upsert_session(fixture_trace.session)
    for step in fixture_trace.steps:
        await postgres_store.insert_step(step)

    results = await postgres_store.search_steps_by_content_identifier("ticket:4471")
    assert len(results) >= 1
    assert all(s.payload.provenance.source_identifier == "ticket:4471" for s in results)
