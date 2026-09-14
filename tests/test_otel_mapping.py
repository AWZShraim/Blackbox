import json
from pathlib import Path

import pytest

from common.schema import Trace
from recorder.exporters.stdout_exporter import StdoutExporter
from recorder.otel_mapping import attributes_for_step, events_for_step, span_name_for_step


@pytest.fixture()
def fixture_trace() -> Trace:
    path = Path(__file__).parent.parent / "scenarios" / "fixtures" / "clean_session.json"
    return Trace.model_validate(json.loads(path.read_text()))


def _flatten_to_text(obj) -> str:
    return json.dumps(obj, default=str)


def test_content_never_appears_in_span_attributes(fixture_trace):
    """I5, the load-bearing one: prompt text, tool arguments, and tool
    results must never be span attributes — only span events."""
    secret_markers = [
        "Look up ticket 4471",  # user message text
        "Hi, I ordered a week ago",  # tool_result content
        "Order #9931 is in transit",  # tool_request argument content
    ]
    for step in fixture_trace.steps:
        attrs = attributes_for_step(fixture_trace.session, step)
        attrs_text = _flatten_to_text(attrs)
        for marker in secret_markers:
            assert marker not in attrs_text, (
                f"content leaked into span ATTRIBUTES for step {step.type.value}: {marker!r}"
            )


def test_content_does_appear_in_span_events_where_expected(fixture_trace):
    model_call_step = next(s for s in fixture_trace.steps if s.type.value == "model_call")
    events = events_for_step(model_call_step)
    events_text = _flatten_to_text(events)
    assert "Look up ticket 4471" in events_text

    tool_result_step = next(s for s in fixture_trace.steps if s.type.value == "tool_result")
    events = events_for_step(tool_result_step)
    events_text = _flatten_to_text(events)
    assert "Hi, I ordered a week ago" in events_text


def test_span_names_follow_gen_ai_convention(fixture_trace):
    model_call_step = next(s for s in fixture_trace.steps if s.type.value == "model_call")
    assert span_name_for_step(model_call_step) == "gen_ai.chat claude-haiku-4-5-20251001"

    tool_request_step = next(s for s in fixture_trace.steps if s.type.value == "tool_request")
    assert span_name_for_step(tool_request_step) == "gen_ai.execute_tool get_ticket"


def test_attributes_carry_human_and_agent_identity(fixture_trace):
    """I7: identity is metadata, not content — fine to be a span attribute."""
    step = fixture_trace.steps[0]
    attrs = attributes_for_step(fixture_trace.session, step)
    assert attrs["blackbox.human_id"] == "user:jane.doe"
    assert attrs["blackbox.agent_id"] == "support-agent"


@pytest.mark.asyncio
async def test_stdout_exporter_runs_without_error(fixture_trace, capsys):
    exporter = StdoutExporter()
    await exporter.export_session(fixture_trace.session)
    for step in fixture_trace.steps:
        await exporter.export_step(fixture_trace.session, step)
    out = capsys.readouterr().out
    assert out.count("\n") == len(fixture_trace.steps)
    first_line = json.loads(out.splitlines()[0])
    assert "name" in first_line and "attributes" in first_line and "events" in first_line
