"""
The mediator core: the ten-step happy path from Section 6.2, decoupled from
HTTP so it is directly unit-testable. mediator/ingress/*.py are thin
adapters that parse HTTP/MCP requests into calls here — they must not
duplicate any of this logic.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from common.interfaces import Collector, CredentialBroker
from common.schema import (
    AgentLifecyclePayload,
    ByteRange,
    ContainmentAction,
    ContainmentEventPayload,
    ContainmentInfo,
    ContextSegment,
    FailMode,
    HumanContext,
    LifecycleEvent,
    Message,
    ModelCallPayload,
    ModelResponsePayload,
    PolicyDecision,
    PolicyDecisionPayload,
    ProvenanceRecord,
    Session,
    SessionStatus,
    SourceType,
    Step,
    StepType,
    TokenCounts,
    ToolCallRequest,
    ToolRequestPayload,
    ToolResultPayload,
    ToolSchema,
    TrustLevel,
    utcnow,
)
from mediator.execution.registry import ToolRegistry
from mediator.execution.sandbox import Sandbox
from mediator.policy.engine import PolicyEngine, PolicyEvaluation
from mediator.providers.base import ModelProvider, ModelResponse

DEFAULT_CREDENTIAL_TTL_SECONDS = 60

# Hard ceilings on model spend, enforced centrally here because every model
# call — live incident runs, the hosted demo (Section 8), manual testing —
# passes through Mediator.handle_model_call. Overridable per Mediator
# instance (e.g. a lower cap for the public demo, Section 8); the defaults
# are deliberately conservative for a project funded out of pocket.
DEFAULT_MAX_TOKENS_PER_CALL = 2048
DEFAULT_MAX_TOKENS_PER_SESSION = 40_000


class TokenBudgetExceeded(Exception):
    """Raised when a session has spent its token budget. Distinct from
    ToolNotAllowed (a policy/containment decision) — this is a cost guard,
    not a security decision, though both end a call the same way."""


class ToolNotAllowed(Exception):
    """Raised when a tool call is denied by policy or blocked by
    containment. Callers (ingress adapters) turn this into the right
    HTTP/MCP error response; the trace already records why."""


class SessionNotFound(Exception):
    pass


def _forced_deny(reason: str) -> PolicyEvaluation:
    return PolicyEvaluation(
        decision=PolicyDecision.deny,
        policy_id="containment",
        rule_matched="post_containment_block",
        reason=reason,
        fail_mode=FailMode.fail_closed,
    )


def _build_context_composition(
    *,
    system_prompt: str | None,
    messages: list[dict[str, Any]],
    provenance_by_call_id: dict[str, ProvenanceRecord],
) -> list[ContextSegment]:
    """Reconstructs, from the conversation the agent sent, which segment of
    context came from where. Every tool_result block is matched back to the
    provenance record the mediator generated when that tool actually ran
    (`provenance_by_call_id`); anything the mediator has no record of is
    tagged untrusted rather than assumed safe. This is what the Context
    Inspector renders (Section 6.5)."""

    segments: list[ContextSegment] = []
    offset = 0

    def add(text: str, provenance: ProvenanceRecord) -> None:
        nonlocal offset
        start = offset
        end = offset + len(text)
        offset = end + 1
        segments.append(ContextSegment(
            provenance=provenance.model_copy(update={"byte_range": ByteRange(start=start, end=end)}),
            text=text,
        ))

    if system_prompt:
        add(system_prompt, ProvenanceRecord(
            source_type=SourceType.system_prompt, trust_level=TrustLevel.trusted,
            byte_range=ByteRange(start=0, end=0),
        ))

    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content
        for block in blocks:
            btype = block.get("type")
            if btype == "text":
                trust = TrustLevel.semi_trusted if role == "user" else TrustLevel.trusted
                source = SourceType.user_input if role == "user" else SourceType.agent_memory
                add(block["text"], ProvenanceRecord(
                    source_type=source, trust_level=trust, byte_range=ByteRange(start=0, end=0),
                ))
            elif btype == "tool_result":
                call_id = block.get("tool_use_id")
                provenance = provenance_by_call_id.get(call_id)
                text = block.get("content", "")
                if not isinstance(text, str):
                    text = str(text)
                if provenance is None:
                    # Unknown provenance must never be assumed trusted.
                    provenance = ProvenanceRecord(
                        source_type=SourceType.tool_result, trust_level=TrustLevel.untrusted,
                        byte_range=ByteRange(start=0, end=0),
                    )
                add(text, provenance)
            # tool_use blocks are the model's own prior output, already
            # captured by that turn's model_response step — not "content
            # that entered context" in the provenance sense.
    return segments


@dataclass
class _SessionState:
    session: Session
    sequence: int = 0
    provenance_by_call_id: dict[str, ProvenanceRecord] = field(default_factory=dict)
    tokens_spent: int = 0

    def next_sequence(self) -> int:
        seq = self.sequence
        self.sequence += 1
        return seq


class Mediator:
    def __init__(
        self,
        *,
        registry: ToolRegistry,
        policy: PolicyEngine,
        credential_broker: CredentialBroker,
        sandbox: Sandbox,
        collector: Collector,
        provider: ModelProvider | None = None,
        max_tokens_per_call: int = DEFAULT_MAX_TOKENS_PER_CALL,
        max_tokens_per_session: int = DEFAULT_MAX_TOKENS_PER_SESSION,
    ) -> None:
        self._registry = registry
        self._policy = policy
        self._credentials = credential_broker
        self._sandbox = sandbox
        self._collector = collector
        self._provider = provider
        self._max_tokens_per_call = max_tokens_per_call
        self._max_tokens_per_session = max_tokens_per_session
        self._sessions: dict[uuid.UUID, _SessionState] = {}

    # -- session lifecycle --------------------------------------------------

    async def create_session(
        self,
        *,
        agent_id: str,
        agent_version: str,
        human_id: str,
        task_description: str,
        human_context: HumanContext | None = None,
        scenario_id: str | None = None,
    ) -> Session:
        session = Session(
            agent_id=agent_id,
            agent_version=agent_version,
            human_id=human_id,
            human_context=human_context or HumanContext(),
            task_description=task_description,
            scenario_id=scenario_id,
        )
        self._sessions[session.session_id] = _SessionState(session=session)
        await self._collector.emit_session(session)
        return session

    def get_session(self, session_id: uuid.UUID) -> Session:
        return self._state(session_id).session

    def _state(self, session_id: uuid.UUID) -> _SessionState:
        state = self._sessions.get(session_id)
        if state is None:
            raise SessionNotFound(str(session_id))
        return state

    def _is_post_containment(self, state: _SessionState) -> bool:
        return state.session.status in (SessionStatus.contained, SessionStatus.terminated)

    async def record_lifecycle_event(
        self, session_id: uuid.UUID, *, event: str, reason: str | None = None, initiated_by: str | None = None,
    ) -> Step:
        """I1: termination is an event WITHIN the trace, never the end of
        it — this method has no branch that refuses to record because the
        session already ended, was contained, or was terminated. A
        supervisor that detects an agent process died unexpectedly calls
        this with event="terminated" independently of the agent (which, by
        construction, may no longer exist to call anything itself)."""
        state = self._state(session_id)
        post_containment = self._is_post_containment(state)
        step = Step(
            session_id=session_id, sequence=state.next_sequence(), type=StepType.agent_lifecycle,
            payload=AgentLifecyclePayload(event=LifecycleEvent(event), reason=reason, initiated_by=initiated_by),
            post_containment=post_containment,
        )
        await self._collector.emit_step(step)

        if event in ("completed", "failed", "terminated"):
            state.session.status = SessionStatus.terminated if event == "terminated" else SessionStatus(event)
            state.session.ended_at = utcnow()
            await self._collector.emit_session(state.session)
        return step

    # -- containment (M9 uses this; wired here so M4's session-state check
    #    already has somewhere real to read from) -------------------------

    async def contain_session(self, session_id: uuid.UUID, *, initiated_by: str, reason: str | None = None) -> None:
        state = self._state(session_id)
        await self._credentials.revoke_session(session_id)

        state.session.status = SessionStatus.contained
        state.session.containment = ContainmentInfo(
            contained_at=utcnow(),
            initiated_by=initiated_by, reason=reason,
            actions=[ContainmentAction.forwarding_stopped, ContainmentAction.credentials_revoked],
        )
        await self._collector.emit_session(state.session)

        for action in (ContainmentAction.forwarding_stopped, ContainmentAction.credentials_revoked):
            step = Step(
                session_id=session_id, sequence=state.next_sequence(), type=StepType.containment_event,
                payload=ContainmentEventPayload(action=action, initiated_by=initiated_by, post_containment=False),
            )
            await self._collector.emit_step(step)

    # -- model traffic (I6) --------------------------------------------------

    async def handle_model_call(
        self,
        *,
        session_id: uuid.UUID,
        model: str,
        system_prompt: str | None,
        messages: list[dict[str, Any]],
        tools_offered: list[dict[str, Any]],
        max_tokens: int = 1024,
    ) -> ModelResponse:
        state = self._state(session_id)
        post_containment = self._is_post_containment(state)

        context_composition = _build_context_composition(
            system_prompt=system_prompt, messages=messages, provenance_by_call_id=state.provenance_by_call_id,
        )

        call_step = Step(
            session_id=session_id, sequence=state.next_sequence(), type=StepType.model_call,
            payload=ModelCallPayload(
                model=model,
                messages=[Message(role=m.get("role", "user"), content=m.get("content")) for m in messages],
                system_prompt=system_prompt,
                tools_offered=[ToolSchema(**t) for t in tools_offered],
                context_composition=context_composition,
            ),
            post_containment=post_containment,
        )
        await self._collector.emit_step(call_step)

        if post_containment:
            raise ToolNotAllowed("session is contained/terminated; LLM forwarding stopped")
        if self._provider is None:
            raise RuntimeError("mediator has no model provider configured")
        if state.tokens_spent >= self._max_tokens_per_session:
            raise TokenBudgetExceeded(
                f"session {session_id} has spent {state.tokens_spent} tokens "
                f"(cap {self._max_tokens_per_session}); no further model calls will be forwarded"
            )

        capped_max_tokens = min(max_tokens, self._max_tokens_per_call)
        response = await self._provider.create_message(
            model=model, system=system_prompt, messages=messages, tools=tools_offered, max_tokens=capped_max_tokens,
        )
        state.tokens_spent += response.input_tokens + response.output_tokens

        response_step = Step(
            session_id=session_id, sequence=state.next_sequence(), type=StepType.model_response,
            parent_step_id=call_step.step_id,
            payload=ModelResponsePayload(
                stop_reason=response.stop_reason,
                text=response.text,
                tool_calls=[
                    ToolCallRequest(tool_call_id=c.id, tool_name=c.name, arguments=c.input)
                    for c in response.tool_calls
                ],
                token_counts=TokenCounts(
                    prompt=response.input_tokens, completion=response.output_tokens,
                    total=response.input_tokens + response.output_tokens,
                ),
            ),
            post_containment=post_containment,
        )
        await self._collector.emit_step(response_step)
        return response

    # -- tool traffic (I6) ---------------------------------------------------

    async def handle_tool_call(
        self,
        *,
        session_id: uuid.UUID,
        tool_name: str,
        arguments: dict[str, Any],
        tool_call_id: str,
        requested_by: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        state = self._state(session_id)
        post_containment = self._is_post_containment(state)

        request_step = Step(
            session_id=session_id, sequence=state.next_sequence(), type=StepType.tool_request,
            parent_step_id=requested_by,
            payload=ToolRequestPayload(
                tool_name=tool_name, arguments=arguments, requested_by=requested_by or state.session.session_id,
            ),
            post_containment=post_containment,
        )
        await self._collector.emit_step(request_step)

        spec = self._registry.get(tool_name)
        in_catalogue = spec is not None
        risk = spec.risk.value if spec else "critical"

        decision_eval = (
            _forced_deny("session is contained/terminated") if post_containment
            else self._policy.evaluate(tool_name=tool_name, arguments=arguments, risk=risk, in_catalogue=in_catalogue)
        )

        decision_step = Step(
            session_id=session_id, sequence=state.next_sequence(), type=StepType.policy_decision,
            parent_step_id=request_step.step_id,
            payload=PolicyDecisionPayload(
                decision=decision_eval.decision, policy_id=decision_eval.policy_id,
                rule_matched=decision_eval.rule_matched, reason=decision_eval.reason,
                fail_mode=decision_eval.fail_mode,
            ),
            post_containment=post_containment,
        )
        await self._collector.emit_step(decision_step)

        if decision_eval.decision != PolicyDecision.allow:
            error = f"{decision_eval.decision.value}: {decision_eval.reason}"
            await self._emit_denied_result(state, request_step, tool_name, error, post_containment)
            raise ToolNotAllowed(error)

        credential = await self._credentials.mint(
            session_id=session_id, tool_name=tool_name, risk=risk, ttl_seconds=DEFAULT_CREDENTIAL_TTL_SECONDS,
        )

        start = time.monotonic()
        sandbox_result = await self._sandbox.execute(
            handler_path=spec.handler_path, arguments=arguments, env={"NORTHWIND_DB_PATH": credential.secret},
        )
        duration_ms = int((time.monotonic() - start) * 1000)

        await self._credentials.revoke(credential.credential_ref)

        trust_level = TrustLevel.untrusted if spec.tool_class.value == "read" else TrustLevel.trusted
        provenance = ProvenanceRecord(
            source_type=SourceType.tool_result, source_step_id=request_step.step_id, source_tool=tool_name,
            source_identifier=_source_identifier(tool_name, arguments),
            trust_level=trust_level, byte_range=ByteRange(start=0, end=len(str(sandbox_result.result or ""))),
        )
        state.provenance_by_call_id[tool_call_id] = provenance

        result_step = Step(
            session_id=session_id, sequence=state.next_sequence(), type=StepType.tool_result, duration_ms=duration_ms,
            parent_step_id=request_step.step_id,
            payload=ToolResultPayload(
                tool_name=tool_name, success=sandbox_result.success, result=sandbox_result.result,
                error=sandbox_result.error, credential_ref=credential.credential_ref,
                sandbox_id=sandbox_result.sandbox_id, provenance=provenance,
            ),
            post_containment=post_containment,
        )
        await self._collector.emit_step(result_step)

        if not sandbox_result.success:
            raise RuntimeError(sandbox_result.error)
        return sandbox_result.result

    async def _emit_denied_result(self, state: _SessionState, request_step: Step, tool_name: str, error: str, post_containment: bool) -> None:
        result_step = Step(
            session_id=state.session.session_id, sequence=state.next_sequence(), type=StepType.tool_result,
            parent_step_id=request_step.step_id,
            payload=ToolResultPayload(
                tool_name=tool_name, success=False, result=None, error=error,
                credential_ref="", sandbox_id="",
                provenance=ProvenanceRecord(
                    source_type=SourceType.tool_result, source_step_id=request_step.step_id, source_tool=tool_name,
                    trust_level=TrustLevel.trusted, byte_range=ByteRange(start=0, end=0),
                ),
            ),
            post_containment=post_containment,
        )
        await self._collector.emit_step(result_step)


def _source_identifier(tool_name: str, arguments: dict[str, Any]) -> str | None:
    if tool_name in ("get_ticket", "update_ticket") and "id" in arguments:
        return f"ticket:{arguments['id']}"
    if tool_name == "search_tickets":
        return f"ticket_search:{arguments.get('query')}"
    if tool_name == "search_docs":
        return f"doc_search:{arguments.get('query')}"
    if tool_name == "get_customer" and "id" in arguments:
        return f"customer:{arguments['id']}"
    return None
