"""
Blackbox trace schema — the source-of-truth contract for every component.

Write this first, before any other code (build spec Section 5). Every
mediator, recorder, detector, and investigator module imports from here
rather than redefining shapes locally.

Internal schema is richer than the OpenTelemetry GenAI semantic conventions
(provenance, detection, and containment have no standard equivalent as of
this build). This module stays the source of truth; recorder/otel_mapping.py
maps it onto gen_ai.* at export time, version-pinned against SCHEMA_VERSION /
GENAI_SEMCONV_VERSION below so a spec change is a single-file edit rather
than a scavenger hunt.

I5: prompt text, tool arguments, and tool results live in step *payloads*
that the recorder emits as OTel span *events*, never as span *attributes*.
Nothing in this module should be flattened into attribute-shaped key/value
pairs at export time — see otel_mapping.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Bump together with recorder/otel_mapping.py when either changes.
SCHEMA_VERSION = "1.0.0"
GENAI_SEMCONV_VERSION = "1.28.0-dev"  # gen_ai.* is still Development status


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _Base(BaseModel):
    """Strict by default: an unrecognized field is a bug in the caller, not
    a thing to silently swallow — this schema is the contract (Section 5)."""

    model_config = ConfigDict(extra="forbid")


class _OpenBase(BaseModel):
    """For genuinely open-ended objects the spec describes only by example
    (e.g. human_context: 'role, team, auth method')."""

    model_config = ConfigDict(extra="allow")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SessionStatus(str, Enum):
    running = "running"
    completed = "completed"
    failed = "failed"
    contained = "contained"
    terminated = "terminated"


class StepType(str, Enum):
    model_call = "model_call"
    model_response = "model_response"
    tool_request = "tool_request"
    tool_result = "tool_result"
    policy_decision = "policy_decision"
    detection_flag = "detection_flag"
    containment_event = "containment_event"
    agent_lifecycle = "agent_lifecycle"


class SourceType(str, Enum):
    user_input = "user_input"
    system_prompt = "system_prompt"
    tool_result = "tool_result"
    agent_memory = "agent_memory"
    sub_agent = "sub_agent"


class TrustLevel(str, Enum):
    """Detection keys off this field (Section 5). Rules, verbatim from spec:
    system prompt and registered tool schemas -> trusted; authenticated user
    input -> semi_trusted; anything retrieved from a data store -> untrusted.
    """

    trusted = "trusted"
    semi_trusted = "semi_trusted"
    untrusted = "untrusted"


class PolicyDecision(str, Enum):
    allow = "allow"
    deny = "deny"
    require_approval = "require_approval"


class FailMode(str, Enum):
    fail_open = "fail_open"
    fail_closed = "fail_closed"


class Severity(str, Enum):
    info = "info"
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ContainmentAction(str, Enum):
    forwarding_stopped = "forwarding_stopped"
    credentials_revoked = "credentials_revoked"
    agent_terminated = "agent_terminated"
    released = "released"


class LifecycleEvent(str, Enum):
    """agent_lifecycle payload events. Termination is an event WITHIN the
    trace (I1) — never modeled as the trace ending. `status` on Session is
    the summary; these events are the audit log that produced it."""

    started = "started"
    completed = "completed"
    failed = "failed"
    terminated = "terminated"
    contained = "contained"
    released = "released"


# ---------------------------------------------------------------------------
# Small shared value objects
# ---------------------------------------------------------------------------


class HumanContext(_OpenBase):
    role: Optional[str] = None
    team: Optional[str] = None
    auth_method: Optional[str] = None


class TokenCounts(_Base):
    prompt: int = 0
    completion: int = 0
    total: int = 0


class ByteRange(_Base):
    """Location of a content segment within the assembled context window,
    in characters (UTF-8 codepoints), not raw model tokens."""

    start: int
    end: int


class ContainmentInfo(_Base):
    """Session-level summary of containment state. The authoritative,
    append-only log is the sequence of `containment_event` steps; this is
    the current-state projection of that log, kept on Session for cheap
    reads (list views, search) without replaying the whole trace."""

    contained_at: datetime
    initiated_by: str
    actions: list[ContainmentAction] = Field(default_factory=list)
    reason: Optional[str] = None
    released_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Provenance (Section 5) — the artifact that makes reasoning-compromise
# investigation possible. Attached to every piece of text that enters the
# model's context.
# ---------------------------------------------------------------------------


class ProvenanceRecord(_Base):
    content_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    source_type: SourceType
    source_step_id: Optional[uuid.UUID] = None
    source_tool: Optional[str] = None
    source_identifier: Optional[str] = None
    trust_level: TrustLevel
    entered_at: datetime = Field(default_factory=utcnow)
    byte_range: ByteRange


class ContextSegment(_Base):
    """One tagged slice of a model_call's assembled context window. The
    Context Inspector (Section 6.5) renders these, not raw message text."""

    provenance: ProvenanceRecord
    text: str


class CandidateTrigger(_Base):
    """I8: a ranked candidate, never a single 'root cause'. See
    detector/triggers.py for the ranking heuristics."""

    step_id: uuid.UUID
    content_id: Optional[uuid.UUID] = None
    score: float = Field(ge=0.0, le=1.0)
    reasoning: str
    signals: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Step payloads — one class per StepType. See Step._check_payload_matches_type
# below for the enforcement that ties `type` to the right payload class.
# ---------------------------------------------------------------------------


class Message(_Base):
    role: str
    content: Any  # str, or Anthropic-style structured content blocks


class ToolSchema(_Base):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


class ModelCallPayload(_Base):
    model: str
    messages: list[Message]
    system_prompt: Optional[str] = None
    tools_offered: list[ToolSchema] = Field(default_factory=list)
    token_counts: TokenCounts = Field(default_factory=TokenCounts)
    context_composition: list[ContextSegment] = Field(default_factory=list)


class ToolCallRequest(_Base):
    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any]


class ModelResponsePayload(_Base):
    stop_reason: str
    text: Optional[str] = None
    tool_calls: list[ToolCallRequest] = Field(default_factory=list)
    token_counts: TokenCounts = Field(default_factory=TokenCounts)


class ToolRequestPayload(_Base):
    tool_name: str
    arguments: dict[str, Any]
    requested_by: uuid.UUID  # step_id of the model_response that requested it


class ToolResultPayload(_Base):
    tool_name: str
    success: bool
    result: Any  # the VERIFIED result, as executed by the mediator
    error: Optional[str] = None
    credential_ref: str
    sandbox_id: str
    provenance: ProvenanceRecord


class PolicyDecisionPayload(_Base):
    decision: PolicyDecision
    policy_id: str
    rule_matched: str
    reason: str
    fail_mode: FailMode


class DetectionFlagPayload(_Base):
    severity: Severity
    detector_id: str
    description: str
    candidate_triggers: list[CandidateTrigger] = Field(default_factory=list)
    # Absent for pure policy detectors (unknown_tool, policy_violation) that
    # never consult a learned baseline.
    baseline_ref: Optional[str] = None


class ContainmentEventPayload(_Base):
    action: ContainmentAction
    initiated_by: str
    post_containment: bool = False


class AgentLifecyclePayload(_Base):
    event: LifecycleEvent
    reason: Optional[str] = None
    initiated_by: Optional[str] = None


StepPayload = Union[
    ModelCallPayload,
    ModelResponsePayload,
    ToolRequestPayload,
    ToolResultPayload,
    PolicyDecisionPayload,
    DetectionFlagPayload,
    ContainmentEventPayload,
    AgentLifecyclePayload,
]

_PAYLOAD_BY_TYPE: dict[StepType, type[BaseModel]] = {
    StepType.model_call: ModelCallPayload,
    StepType.model_response: ModelResponsePayload,
    StepType.tool_request: ToolRequestPayload,
    StepType.tool_result: ToolResultPayload,
    StepType.policy_decision: PolicyDecisionPayload,
    StepType.detection_flag: DetectionFlagPayload,
    StepType.containment_event: ContainmentEventPayload,
    StepType.agent_lifecycle: AgentLifecyclePayload,
}


# ---------------------------------------------------------------------------
# Step and Session
# ---------------------------------------------------------------------------


class Step(_Base):
    step_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    session_id: uuid.UUID
    sequence: int
    type: StepType
    started_at: datetime = Field(default_factory=utcnow)
    duration_ms: int = 0
    parent_step_id: Optional[uuid.UUID] = None
    payload: StepPayload
    # True for any step emitted after containment/termination for this
    # session (I1, I9's post-containment demo beat). Set by the mediator /
    # recorder at emit time, not by callers constructing a step by hand.
    post_containment: bool = False

    @model_validator(mode="before")
    @classmethod
    def _coerce_payload(cls, data: Any) -> Any:
        if isinstance(data, dict):
            step_type = data.get("type")
            payload = data.get("payload")
            if isinstance(payload, dict) and step_type is not None:
                expected = _PAYLOAD_BY_TYPE.get(StepType(step_type))
                if expected is not None:
                    data = {**data, "payload": expected.model_validate(payload)}
        return data

    @model_validator(mode="after")
    def _check_payload_matches_type(self) -> "Step":
        expected = _PAYLOAD_BY_TYPE.get(self.type)
        if expected is not None and not isinstance(self.payload, expected):
            raise ValueError(
                f"step.type={self.type!r} requires payload of type "
                f"{expected.__name__}, got {type(self.payload).__name__}"
            )
        return self


class Session(_Base):
    session_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    agent_id: str
    agent_version: str
    human_id: str  # REQUIRED — I7, human identity bound to every session
    human_context: HumanContext = Field(default_factory=HumanContext)
    task_description: str
    started_at: datetime = Field(default_factory=utcnow)
    ended_at: Optional[datetime] = None
    status: SessionStatus = SessionStatus.running
    containment: Optional[ContainmentInfo] = None
    scenario_id: Optional[str] = None


class Trace(_Base):
    """Convenience aggregate used by fixtures, the replay endpoint (I9), and
    incident export. Not itself part of the wire protocol between mediator
    and recorder — those exchange Session/Step individually."""

    session: Session
    steps: list[Step] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# JSON Schema generation — `python -m common.schema` regenerates schema.json
# ---------------------------------------------------------------------------

_TOP_LEVEL_MODELS: list[type[BaseModel]] = [
    Session,
    Step,
    Trace,
    ProvenanceRecord,
    ContextSegment,
    CandidateTrigger,
    ModelCallPayload,
    ModelResponsePayload,
    ToolRequestPayload,
    ToolResultPayload,
    PolicyDecisionPayload,
    DetectionFlagPayload,
    ContainmentEventPayload,
    AgentLifecyclePayload,
]


def generate_json_schema() -> dict[str, Any]:
    from pydantic.json_schema import models_json_schema

    pairs = [(m, "validation") for m in _TOP_LEVEL_MODELS]
    _, top_level = models_json_schema(pairs, title="Blackbox Trace Schema")
    top_level["$id"] = "https://blackbox.internal/schema/trace.schema.json"
    top_level["schema_version"] = SCHEMA_VERSION
    top_level["genai_semconv_version"] = GENAI_SEMCONV_VERSION
    return top_level


def write_json_schema(path: str = "common/schema.json") -> None:
    import json

    with open(path, "w") as f:
        json.dump(generate_json_schema(), f, indent=2, sort_keys=True)
        f.write("\n")


if __name__ == "__main__":
    write_json_schema()
    print("wrote common/schema.json")
