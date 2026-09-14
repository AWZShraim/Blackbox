import json
import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError

from common import interfaces
from common.schema import (
    AgentLifecyclePayload,
    ByteRange,
    ModelCallPayload,
    ProvenanceRecord,
    Session,
    SourceType,
    Step,
    StepType,
    Trace,
    TrustLevel,
    generate_json_schema,
)

FIXTURE = Path(__file__).parent.parent / "scenarios" / "fixtures" / "clean_session.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text())


def test_fixture_trace_round_trips():
    raw = load_fixture()
    trace = Trace.model_validate(raw)

    assert trace.session.human_id == "user:jane.doe"  # I7
    assert len(trace.steps) == 11
    assert trace.steps[0].type == StepType.agent_lifecycle

    # Round-trip through JSON: dump -> parse -> re-validate -> identical.
    dumped = json.loads(trace.model_dump_json())
    trace2 = Trace.model_validate(dumped)
    assert trace2 == trace


def test_untrusted_tool_result_carries_provenance():
    trace = Trace.model_validate(load_fixture())
    tool_result_steps = [s for s in trace.steps if s.type == StepType.tool_result]
    ticket_result = tool_result_steps[0]
    assert ticket_result.payload.provenance.trust_level == TrustLevel.untrusted
    assert ticket_result.payload.provenance.source_identifier == "ticket:4471"


def test_context_composition_tags_every_segment_with_provenance():
    trace = Trace.model_validate(load_fixture())
    model_calls = [s for s in trace.steps if s.type == StepType.model_call]
    for step in model_calls:
        assert isinstance(step.payload, ModelCallPayload)
        for segment in step.payload.context_composition:
            assert segment.provenance.trust_level in (
                TrustLevel.trusted,
                TrustLevel.semi_trusted,
                TrustLevel.untrusted,
            )


def test_step_payload_must_match_declared_type():
    session_id = uuid.uuid4()
    with pytest.raises(ValidationError):
        Step(
            session_id=session_id,
            sequence=0,
            type=StepType.model_call,
            payload=AgentLifecyclePayload(event="started"),
        )


def test_step_type_dict_payload_is_coerced_to_correct_model():
    session_id = uuid.uuid4()
    step = Step.model_validate(
        {
            "session_id": str(session_id),
            "sequence": 0,
            "type": "agent_lifecycle",
            "payload": {"event": "terminated", "reason": "contained", "initiated_by": "user:soc"},
        }
    )
    assert isinstance(step.payload, AgentLifecyclePayload)
    assert step.payload.event.value == "terminated"


def test_session_requires_human_id():
    with pytest.raises(ValidationError):
        Session.model_validate(
            {
                "agent_id": "a",
                "agent_version": "0.1.0",
                "task_description": "no human_id",
            }
        )


def test_termination_is_an_event_not_a_trace_end():
    """I1: after termination the trace stays open. Modeled by
    agent_lifecycle events living inside `steps`, with Session.ended_at
    remaining settable independently of any single lifecycle event."""
    session_id = uuid.uuid4()
    terminated_step = Step(
        session_id=session_id,
        sequence=99,
        type=StepType.agent_lifecycle,
        payload=AgentLifecyclePayload(event="terminated", initiated_by="user:soc"),
    )
    # A further step after termination is not just legal, it's expected —
    # this is exactly what post_containment marks.
    refused_step = Step(
        session_id=session_id,
        sequence=100,
        type=StepType.agent_lifecycle,
        payload=AgentLifecyclePayload(event="completed"),
        post_containment=True,
    )
    assert terminated_step.sequence < refused_step.sequence
    assert refused_step.post_containment is True


def test_trust_level_rules_are_representable():
    system_prompt_prov = ProvenanceRecord(
        source_type=SourceType.system_prompt,
        trust_level=TrustLevel.trusted,
        byte_range=ByteRange(start=0, end=1),
    )
    user_input_prov = ProvenanceRecord(
        source_type=SourceType.user_input,
        trust_level=TrustLevel.semi_trusted,
        byte_range=ByteRange(start=0, end=1),
    )
    retrieved_prov = ProvenanceRecord(
        source_type=SourceType.tool_result,
        trust_level=TrustLevel.untrusted,
        byte_range=ByteRange(start=0, end=1),
    )
    assert system_prompt_prov.trust_level == TrustLevel.trusted
    assert user_input_prov.trust_level == TrustLevel.semi_trusted
    assert retrieved_prov.trust_level == TrustLevel.untrusted


def test_json_schema_generates_without_a_model():
    schema = generate_json_schema()
    assert "$defs" in schema
    def_names = set(schema["$defs"].keys())
    for name in ("Session", "Step", "ProvenanceRecord", "CandidateTrigger"):
        assert any(name in d for d in def_names), f"{name} missing from generated schema"


def test_interfaces_import_cleanly_and_are_protocols():
    import typing

    for proto in (interfaces.Collector, interfaces.CredentialBroker, interfaces.Exporter):
        assert typing.get_origin(proto) is None
        assert hasattr(proto, "_is_protocol") and proto._is_protocol


def test_credential_broker_protocol_is_structurally_checkable():
    class FakeBroker:
        async def mint(self, *, session_id, tool_name, risk, ttl_seconds):
            return interfaces.ScopedCredential(
                credential_ref="ref", secret="s", expires_at=None, metadata={}
            )

        async def revoke(self, credential_ref):
            return None

        async def revoke_session(self, session_id):
            return None

    assert isinstance(FakeBroker(), interfaces.CredentialBroker)
