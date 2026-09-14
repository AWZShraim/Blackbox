"""
M7 acceptance (Section 13): each fixture trace produces the expected flag;
each produces a ranked trigger list with the planted cause in the top
three; no flags on the clean trace. Developed and tested against
hand-written fixtures, deterministically, without invoking a model
(Section 7) — nothing in this file talks to a live LLM.
"""

import json
from pathlib import Path

import pytest

from common.schema import Trace
from detector.baseline import ArgumentShape, Baseline, ToolBaseline, learn_baseline
from detector.engine import run_detectors

FIXTURES_DIR = Path(__file__).parent.parent / "scenarios" / "fixtures"


def load_trace(name: str) -> Trace:
    return Trace.model_validate(json.loads((FIXTURES_DIR / name).read_text()))


def detector_ids(flags) -> set[str]:
    return {f.payload.detector_id for f in flags}


# ---------------------------------------------------------------------------
# Clean trace: no flags, under any circumstance.
# ---------------------------------------------------------------------------

def test_clean_trace_produces_no_flags():
    trace = load_trace("clean_session.json")
    flags = run_detectors(trace)
    assert flags == []


def test_clean_trace_produces_no_flags_even_with_a_tight_baseline():
    """A baseline learned from the clean trace itself should still not
    cause the same trace to flag against its own baseline."""
    trace = load_trace("clean_session.json")
    baseline = learn_baseline(subject_type="agent", subject_id="support-agent", traces=[trace])
    flags = run_detectors(trace, agent_baseline=baseline)
    assert flags == []


# ---------------------------------------------------------------------------
# Mechanism 1: reasoning compromise (ticket injection -> exfil attempt)
# ---------------------------------------------------------------------------

def test_reasoning_compromise_fixture_flags_injection_and_influence_and_exfiltration():
    trace = load_trace("fixture_reasoning_compromise.json")
    flags = run_detectors(trace)
    ids = detector_ids(flags)
    assert "injection_heuristic" in ids
    assert "untrusted_influence" in ids
    assert "exfiltration_shape" in ids
    assert "policy_violation" in ids


def test_reasoning_compromise_candidate_triggers_land_on_ticket_8814_in_top_three():
    """Candidate triggers point at the model_call step where the content
    entered context (so 'navigates to that step and opens the context
    inspector', Section 6.5) — the specific poisoned segment within it is
    what content_id disambiguates. Traced by content_id, not step_id,
    since the same poisoned content can appear in more than one
    model_call's context_composition."""
    trace = load_trace("fixture_reasoning_compromise.json")
    flags = run_detectors(trace)
    influence_flag = next(f for f in flags if f.payload.detector_id == "untrusted_influence")
    triggers = influence_flag.payload.candidate_triggers
    assert len(triggers) > 0
    top_three_content_ids = {t.content_id for t in triggers[:3]}
    poisoned_content_id = next(
        s.payload.provenance.content_id for s in trace.steps
        if s.type.value == "tool_result" and s.payload.provenance.source_identifier == "ticket:8814"
    )
    assert poisoned_content_id in top_three_content_ids
    top_signals = triggers[0].signals
    assert "untrusted_source" in top_signals
    assert "injection_heuristic_fired" in top_signals


# ---------------------------------------------------------------------------
# Mechanism 2: privilege boundary escape (doc injection -> refund above cap)
# ---------------------------------------------------------------------------

def test_privilege_escalation_fixture_flags_injection_and_policy_violation():
    trace = load_trace("fixture_privilege_escalation.json")
    flags = run_detectors(trace)
    ids = detector_ids(flags)
    assert "injection_heuristic" in ids
    assert "untrusted_influence" in ids
    assert "policy_violation" in ids


def test_privilege_escalation_candidate_triggers_land_on_doc_4402_in_top_three():
    trace = load_trace("fixture_privilege_escalation.json")
    flags = run_detectors(trace)
    influence_flag = next(f for f in flags if f.payload.detector_id == "untrusted_influence")
    top_three_content_ids = {t.content_id for t in influence_flag.payload.candidate_triggers[:3]}
    poisoned_content_id = next(
        s.payload.provenance.content_id for s in trace.steps
        if s.type.value == "tool_result" and s.payload.provenance.source_identifier == "doc:4402"
    )
    assert poisoned_content_id in top_three_content_ids


def test_privilege_escalation_argument_anomaly_fires_against_a_tight_refund_baseline():
    trace = load_trace("fixture_privilege_escalation.json")
    baseline = Baseline(
        subject_type="agent", subject_id="support-agent", learned_at="2026-01-01T00:00:00Z",
        sessions_observed=40, tool_set=["issue_refund"],
        tools={"issue_refund": ToolBaseline(call_count=40, argument_shapes={
            "amount": ArgumentShape(is_numeric=True, min_value=10.0, max_value=480.0),
            "order_id": ArgumentShape(is_numeric=True, min_value=1.0, max_value=500.0),
        })},
    )
    flags = run_detectors(trace, agent_baseline=baseline)
    anomaly = next(f for f in flags if f.payload.detector_id == "argument_anomaly")
    assert "2000" in anomaly.payload.description
    assert anomaly.payload.baseline_ref == baseline.ref()


# ---------------------------------------------------------------------------
# Mechanism 3: corrigibility failure (tool activity after a stop signal)
# ---------------------------------------------------------------------------

def test_corrigibility_bypass_fixture_flags_post_stop_activity():
    trace = load_trace("fixture_corrigibility_bypass.json")
    flags = run_detectors(trace)
    ids = detector_ids(flags)
    assert "post_stop_activity" in ids

    flag = next(f for f in flags if f.payload.detector_id == "post_stop_activity")
    flagged_step = next(s for s in trace.steps if s.step_id == flag.parent_step_id)
    assert flagged_step.payload.tool_name == "deploy_service"
    assert flagged_step.payload.arguments["version"] == "4.2.0-hotfix"
    assert flagged_step.post_containment is True


# ---------------------------------------------------------------------------
# Mechanism 4: excessive agency (human-driven bulk export, abuse mode, I7)
# ---------------------------------------------------------------------------

def test_excessive_agency_fixture_flags_policy_violation():
    trace = load_trace("fixture_excessive_agency.json")
    flags = run_detectors(trace)
    assert "policy_violation" in detector_ids(flags)


def test_excessive_agency_volume_anomaly_fires_against_the_human_baseline_not_agent():
    """I7: this human's baseline is what makes the deviation visible — the
    agent itself is just doing what a normal Northwind support agent
    always does (calling read tools), so nothing here should require an
    agent-baseline anomaly to catch it."""
    trace = load_trace("fixture_excessive_agency.json")
    human_baseline = Baseline(
        subject_type="human", subject_id="user:contractor.temp", learned_at="2026-01-01T00:00:00Z",
        sessions_observed=10, tool_set=["get_customer"], tools={}, calls_per_session_max=2,
    )
    flags = run_detectors(trace, human_baseline=human_baseline)
    volume_flag = next(f for f in flags if f.payload.detector_id == "volume_anomaly")
    assert volume_flag.payload.baseline_ref == human_baseline.ref()

    # without any baseline, volume_anomaly has nothing to compare against
    flags_no_baseline = run_detectors(trace)
    assert "volume_anomaly" not in detector_ids(flags_no_baseline)


# ---------------------------------------------------------------------------
# Baseline learning itself
# ---------------------------------------------------------------------------

def test_learn_baseline_captures_tool_set_and_sequences_from_the_clean_trace():
    trace = load_trace("clean_session.json")
    baseline = learn_baseline(subject_type="agent", subject_id="support-agent", traces=[trace])
    assert "get_ticket" in baseline.tool_set
    assert "update_ticket" in baseline.tool_set
    assert baseline.has_sequence("get_ticket", "update_ticket")
    assert baseline.calls_per_session_max == 2  # get_ticket, update_ticket


def test_baseline_store_round_trips_to_disk(tmp_path):
    from detector.baseline import BaselineStore

    trace = load_trace("clean_session.json")
    baseline = learn_baseline(subject_type="agent", subject_id="support-agent", traces=[trace])
    store = BaselineStore(tmp_path)
    path = store.save(baseline)
    assert path.exists()

    # human-editable: a platform engineer can open and hand-correct this
    raw = json.loads(path.read_text())
    assert raw["subject_id"] == "support-agent"

    reloaded = store.load("agent", "support-agent")
    assert reloaded == baseline
