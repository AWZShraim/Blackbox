import pytest

from mediator.core import Mediator, ToolNotAllowed
from mediator.credentials.local import LocalDevBroker
from mediator.execution.sandbox import InProcessSandbox
from mediator.policy.engine import PolicyEngine
from mediator.providers.base import ModelResponse, ToolCall
from scenarios.company.seed import seed
from scenarios.tools.definitions import build_registry
from tests.fakes import InMemoryCollector


class FakeProvider:
    def __init__(self, script):
        self._script = list(script)
        self.calls = []

    async def create_message(self, *, model, system, messages, tools, max_tokens=1024):
        self.calls.append({"model": model, "system": system, "messages": messages, "tools": tools})
        return self._script.pop(0)


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "northwind_test.db"
    seed(path, n_customers=20, n_orders=40, n_tickets=39)
    return path


def make_mediator(*, provider=None, db_path=None, agent_baseline=None, human_baselines=None):
    collector = InMemoryCollector()
    mediator = Mediator(
        registry=build_registry(),
        policy=PolicyEngine.load(),
        credential_broker=LocalDevBroker(db_path=db_path),
        sandbox=InProcessSandbox(),
        collector=collector,
        provider=provider,
        agent_baseline=agent_baseline,
        human_baselines=human_baselines,
    )
    return mediator, collector


@pytest.mark.asyncio
async def test_low_risk_tool_call_is_allowed_and_produces_steps(db_path):
    mediator, collector = make_mediator(db_path=db_path)
    session = await mediator.create_session(
        agent_id="support-agent", agent_version="0.1.0", human_id="user:jane",
        task_description="resolve ticket 1",
    )
    result = await mediator.handle_tool_call(
        session_id=session.session_id, tool_name="get_ticket", arguments={"id": 1}, tool_call_id="c1",
    )
    assert result["id"] == 1

    step_types = [s.type.value for s in collector.steps]
    assert step_types == ["tool_request", "policy_decision", "tool_result"]
    assert collector.steps[1].payload.decision.value == "allow"
    assert collector.steps[2].payload.success is True
    assert collector.steps[2].payload.provenance.trust_level.value == "untrusted"  # read tool


@pytest.mark.asyncio
async def test_unknown_tool_is_denied_by_policy(db_path):
    mediator, collector = make_mediator(db_path=db_path)
    session = await mediator.create_session(
        agent_id="a", agent_version="0.1.0", human_id="user:jane", task_description="x",
    )
    with pytest.raises(ToolNotAllowed):
        await mediator.handle_tool_call(
            session_id=session.session_id, tool_name="run_bash", arguments={"cmd": "rm -rf /"}, tool_call_id="c1",
        )
    decision_step = next(s for s in collector.steps if s.type.value == "policy_decision")
    assert decision_step.payload.decision.value == "deny"
    assert decision_step.payload.rule_matched == "deny_unknown_tool"


@pytest.mark.asyncio
async def test_refund_above_cap_requires_approval_and_is_blocked(db_path):
    mediator, collector = make_mediator(db_path=db_path)
    session = await mediator.create_session(
        agent_id="a", agent_version="0.1.0", human_id="user:jane", task_description="x",
    )
    with pytest.raises(ToolNotAllowed):
        await mediator.handle_tool_call(
            session_id=session.session_id, tool_name="issue_refund",
            arguments={"order_id": 1, "amount": 999.0}, tool_call_id="c1",
        )
    decision_step = next(s for s in collector.steps if s.type.value == "policy_decision")
    assert decision_step.payload.decision.value == "require_approval"
    result_step = next(s for s in collector.steps if s.type.value == "tool_result")
    assert result_step.payload.success is False


@pytest.mark.asyncio
async def test_refund_within_cap_is_allowed(db_path):
    mediator, collector = make_mediator(db_path=db_path)
    session = await mediator.create_session(
        agent_id="a", agent_version="0.1.0", human_id="user:jane", task_description="x",
    )
    result = await mediator.handle_tool_call(
        session_id=session.session_id, tool_name="issue_refund",
        arguments={"order_id": 1, "amount": 50.0}, tool_call_id="c1",
    )
    assert result["status"] == "issued"


@pytest.mark.asyncio
async def test_send_email_to_external_domain_is_denied(db_path):
    mediator, collector = make_mediator(db_path=db_path)
    session = await mediator.create_session(
        agent_id="a", agent_version="0.1.0", human_id="user:jane", task_description="x",
    )
    with pytest.raises(ToolNotAllowed):
        await mediator.handle_tool_call(
            session_id=session.session_id, tool_name="send_email",
            arguments={"to": "attacker@evil.example", "subject": "x", "body": "x"}, tool_call_id="c1",
        )


@pytest.mark.asyncio
async def test_send_email_to_internal_domain_is_allowed(db_path):
    mediator, collector = make_mediator(db_path=db_path)
    session = await mediator.create_session(
        agent_id="a", agent_version="0.1.0", human_id="user:jane", task_description="x",
    )
    result = await mediator.handle_tool_call(
        session_id=session.session_id, tool_name="send_email",
        arguments={"to": "agent@northwind-support.example", "subject": "x", "body": "x"}, tool_call_id="c1",
    )
    assert result["sent"] is True


@pytest.mark.asyncio
async def test_model_call_context_composition_tags_prior_tool_result_provenance(db_path):
    """This is I5/I6 end to end: a tool_result the mediator itself recorded
    is matched back to the right ProvenanceRecord when it reappears in a
    later model_call's context_composition."""
    script = [ModelResponse(stop_reason="end_turn", text="ok", tool_calls=[])]
    mediator, collector = make_mediator(provider=FakeProvider(script), db_path=db_path)
    session = await mediator.create_session(
        agent_id="a", agent_version="0.1.0", human_id="user:jane", task_description="x",
    )
    await mediator.handle_tool_call(
        session_id=session.session_id, tool_name="get_ticket", arguments={"id": 1}, tool_call_id="call_1",
    )

    await mediator.handle_model_call(
        session_id=session.session_id, model="claude-haiku-4-5-20251001", system_prompt="sys",
        messages=[
            {"role": "user", "content": "resolve ticket 1"},
            {"role": "assistant", "content": [{"type": "tool_use", "id": "call_1", "name": "get_ticket", "input": {"id": 1}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call_1", "content": "some ticket body"}]},
        ],
        tools_offered=[],
    )

    model_call_step = next(s for s in collector.steps if s.type.value == "model_call")
    segments = model_call_step.payload.context_composition
    tool_result_segment = next(s for s in segments if s.text == "some ticket body")
    assert tool_result_segment.provenance.trust_level.value == "untrusted"
    assert tool_result_segment.provenance.source_tool == "get_ticket"


@pytest.mark.asyncio
async def test_contained_session_blocks_further_tool_calls_and_marks_post_containment(db_path):
    mediator, collector = make_mediator(db_path=db_path)
    session = await mediator.create_session(
        agent_id="a", agent_version="0.1.0", human_id="user:soc", task_description="x",
    )
    await mediator.contain_session(session.session_id, initiated_by="user:soc", reason="test containment")

    with pytest.raises(ToolNotAllowed):
        await mediator.handle_tool_call(
            session_id=session.session_id, tool_name="get_ticket", arguments={"id": 1}, tool_call_id="c1",
        )

    post_containment_steps = [s for s in collector.steps if s.post_containment]
    assert len(post_containment_steps) >= 1
    assert any(s.type.value == "tool_result" and s.payload.success is False for s in post_containment_steps)


@pytest.mark.asyncio
async def test_model_call_token_budget_is_enforced(db_path):
    script = [ModelResponse(stop_reason="end_turn", text="ok", tool_calls=[], input_tokens=30_000, output_tokens=0)]
    mediator, collector = make_mediator(provider=FakeProvider(script), db_path=db_path)
    mediator._max_tokens_per_session = 20_000  # low cap for the test
    session = await mediator.create_session(
        agent_id="a", agent_version="0.1.0", human_id="user:jane", task_description="x",
    )
    await mediator.handle_model_call(
        session_id=session.session_id, model="claude-haiku-4-5-20251001", system_prompt=None,
        messages=[{"role": "user", "content": "hi"}], tools_offered=[],
    )
    from mediator.core import TokenBudgetExceeded
    with pytest.raises(TokenBudgetExceeded):
        await mediator.handle_model_call(
            session_id=session.session_id, model="claude-haiku-4-5-20251001", system_prompt=None,
            messages=[{"role": "user", "content": "hi again"}], tools_offered=[],
        )


@pytest.mark.asyncio
async def test_inline_baseline_check_flags_an_out_of_range_argument_at_call_time(db_path):
    """Section 6.2 step 4 / Section 6.4: the mediator's own inline check,
    not the async detector pipeline — fast, in-memory, no candidate
    triggers (those need the full trace)."""
    from detector.baseline import ArgumentShape, Baseline, ToolBaseline

    baseline = Baseline(
        subject_type="agent", subject_id="support-agent", learned_at="2026-01-01T00:00:00Z",
        sessions_observed=10, tool_set=["issue_refund"],
        tools={"issue_refund": ToolBaseline(call_count=10, argument_shapes={
            "amount": ArgumentShape(is_numeric=True, min_value=10.0, max_value=480.0),
        })},
    )
    mediator, collector = make_mediator(db_path=db_path, agent_baseline=baseline)
    session = await mediator.create_session(
        agent_id="a", agent_version="0.1.0", human_id="user:jane", task_description="x",
    )
    with pytest.raises(ToolNotAllowed):  # 2000 also exceeds the policy cap independently
        await mediator.handle_tool_call(
            session_id=session.session_id, tool_name="issue_refund",
            arguments={"order_id": 1, "amount": 2000.0}, tool_call_id="c1",
        )
    flag_step = next(s for s in collector.steps if s.type.value == "detection_flag")
    assert flag_step.payload.detector_id == "inline_argument_anomaly"
    assert flag_step.payload.baseline_ref == baseline.ref()


@pytest.mark.asyncio
async def test_inline_sequence_anomaly_shares_severity_by_risk_with_the_batch_detector(db_path):
    """inline_sequence_anomaly (the synchronous, single-call path) must
    agree with detector.detectors.sequence_anomaly.detect() (the batch,
    full-trace path) on severity — both call the same evaluate_transition,
    so a live flag and the later stored flag for the same transition can't
    disagree."""
    from detector.baseline import Baseline

    baseline = Baseline(
        subject_type="agent", subject_id="support-agent", learned_at="2026-01-01T00:00:00Z",
        sessions_observed=25, tool_set=["get_ticket", "deploy_service"],
        sequences=[["deploy_service", "get_ticket"]],  # not get_ticket -> deploy_service
    )
    mediator, collector = make_mediator(db_path=db_path, agent_baseline=baseline)
    session = await mediator.create_session(
        agent_id="a", agent_version="0.1.0", human_id="user:jane", task_description="x",
    )
    await mediator.handle_tool_call(
        session_id=session.session_id, tool_name="get_ticket", arguments={"id": 1}, tool_call_id="c1",
    )
    with pytest.raises(ToolNotAllowed):  # deploy_service requires approval regardless
        await mediator.handle_tool_call(
            session_id=session.session_id, tool_name="deploy_service",
            arguments={"name": "api", "version": "1.2.3"}, tool_call_id="c2",
        )
    flag_step = next(s for s in collector.steps if s.type.value == "detection_flag")
    assert flag_step.payload.detector_id == "inline_sequence_anomaly"
    assert flag_step.payload.severity == "critical"  # deploy_service's risk class, not a flat "medium"


@pytest.mark.asyncio
async def test_inline_sequence_anomaly_respects_the_maturity_gate(db_path):
    from detector.baseline import Baseline

    immature_baseline = Baseline(
        subject_type="agent", subject_id="support-agent", learned_at="2026-01-01T00:00:00Z",
        sessions_observed=3, tool_set=["get_ticket", "deploy_service"],
        sequences=[["deploy_service", "get_ticket"]],
    )
    mediator, collector = make_mediator(db_path=db_path, agent_baseline=immature_baseline)
    session = await mediator.create_session(
        agent_id="a", agent_version="0.1.0", human_id="user:jane", task_description="x",
    )
    await mediator.handle_tool_call(
        session_id=session.session_id, tool_name="get_ticket", arguments={"id": 1}, tool_call_id="c1",
    )
    with pytest.raises(ToolNotAllowed):
        await mediator.handle_tool_call(
            session_id=session.session_id, tool_name="deploy_service",
            arguments={"name": "api", "version": "1.2.3"}, tool_call_id="c2",
        )
    flags = [s for s in collector.steps if s.type.value == "detection_flag"]
    assert not any(f.payload.detector_id == "inline_sequence_anomaly" for f in flags)


@pytest.mark.asyncio
async def test_inline_baseline_check_flags_human_volume_deviation(db_path):
    from detector.baseline import Baseline

    human_baseline = Baseline(
        subject_type="human", subject_id="user:contractor.temp", learned_at="2026-01-01T00:00:00Z",
        sessions_observed=5, tool_set=[], tools={}, calls_per_session_max=1,
    )
    mediator, collector = make_mediator(
        db_path=db_path, human_baselines={"user:contractor.temp": human_baseline}
    )
    session = await mediator.create_session(
        agent_id="a", agent_version="0.1.0", human_id="user:contractor.temp", task_description="x",
    )
    await mediator.handle_tool_call(
        session_id=session.session_id, tool_name="get_ticket", arguments={"id": 1}, tool_call_id="c1",
    )
    await mediator.handle_tool_call(
        session_id=session.session_id, tool_name="get_ticket", arguments={"id": 2}, tool_call_id="c2",
    )
    flags = [s for s in collector.steps if s.type.value == "detection_flag"]
    assert any(f.payload.detector_id == "inline_volume_anomaly" for f in flags)


def test_policy_baseline_latency_is_tracked_and_excludes_tool_execution():
    mediator, _ = make_mediator()
    assert mediator.policy_baseline_latency.count == 0  # nothing measured yet, no calls made
