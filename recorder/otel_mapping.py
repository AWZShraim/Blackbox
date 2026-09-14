"""
Maps Blackbox's internal schema onto OpenTelemetry GenAI semantic
conventions (`gen_ai.*`). Version-pinned against GENAI_SEMCONV_VERSION in
common/schema.py — as of this build those conventions are Development
status and live in a separate `semantic-conventions-genai` repository
(Section 5). Isolating the mapping in this one module means a spec change
is a single-file edit, not a scavenger hunt through the recorder.

I5, enforced here structurally: `attributes_for_step` returns only
indexed, size-limited metadata — never prompt text, tool arguments, or tool
results. Anything that is actual content lives in `events_for_step`
instead, matching OTel span *events*, not span *attributes*.
"""

from __future__ import annotations

from typing import Any

from common.schema import GENAI_SEMCONV_VERSION, Session, Step, StepType


def span_name_for_step(step: Step) -> str:
    if step.type == StepType.model_call:
        return f"gen_ai.chat {step.payload.model}"
    if step.type == StepType.tool_request:
        return f"gen_ai.execute_tool {step.payload.tool_name}"
    return f"blackbox.{step.type.value}"


def attributes_for_step(session: Session, step: Step) -> dict[str, Any]:
    """Indexed, size-limited metadata ONLY — never content (I5)."""
    attrs: dict[str, Any] = {
        "gen_ai.semconv.version": GENAI_SEMCONV_VERSION,
        "blackbox.session_id": str(session.session_id),
        "blackbox.agent_id": session.agent_id,
        "blackbox.human_id": session.human_id,  # identity (I7), not content
        "blackbox.step_type": step.type.value,
        "blackbox.sequence": step.sequence,
        "blackbox.post_containment": step.post_containment,
    }
    payload = step.payload
    if step.type == StepType.model_call:
        attrs["gen_ai.operation.name"] = "chat"
        attrs["gen_ai.request.model"] = payload.model
    elif step.type == StepType.model_response:
        attrs["gen_ai.response.finish_reasons"] = [payload.stop_reason]
        attrs["gen_ai.usage.input_tokens"] = payload.token_counts.prompt
        attrs["gen_ai.usage.output_tokens"] = payload.token_counts.completion
    elif step.type == StepType.tool_request:
        attrs["gen_ai.tool.name"] = payload.tool_name
    elif step.type == StepType.tool_result:
        attrs["gen_ai.tool.name"] = payload.tool_name
        attrs["blackbox.tool.success"] = payload.success
        attrs["blackbox.trust_level"] = payload.provenance.trust_level.value
    elif step.type == StepType.policy_decision:
        attrs["blackbox.policy.decision"] = payload.decision.value
        attrs["blackbox.policy.rule_matched"] = payload.rule_matched
    elif step.type == StepType.detection_flag:
        attrs["blackbox.detector_id"] = payload.detector_id
        attrs["blackbox.severity"] = payload.severity.value
    elif step.type == StepType.containment_event:
        attrs["blackbox.containment.action"] = payload.action.value
    return attrs


def events_for_step(step: Step) -> list[dict[str, Any]]:
    """I5: content lives here, as span events — never as attributes. Each
    entry is {name, attributes} shaped for OTel's `span.add_event`."""
    payload = step.payload
    events: list[dict[str, Any]] = []

    if step.type == StepType.model_call:
        events.append({
            "name": "gen_ai.content.prompt",
            "attributes": {
                "gen_ai.prompt": [m.model_dump(mode="json") for m in payload.messages],
                "gen_ai.system_prompt": payload.system_prompt,
                "blackbox.context_composition": [c.model_dump(mode="json") for c in payload.context_composition],
            },
        })
    elif step.type == StepType.model_response:
        events.append({
            "name": "gen_ai.content.completion",
            "attributes": {
                "gen_ai.completion.text": payload.text,
                "gen_ai.completion.tool_calls": [c.model_dump(mode="json") for c in payload.tool_calls],
            },
        })
    elif step.type == StepType.tool_request:
        events.append({
            "name": "gen_ai.tool.arguments",
            "attributes": {"arguments": payload.arguments},
        })
    elif step.type == StepType.tool_result:
        events.append({
            "name": "gen_ai.tool.result",
            "attributes": {
                "result": payload.result,
                "error": payload.error,
                "provenance": payload.provenance.model_dump(mode="json"),
            },
        })
    elif step.type == StepType.detection_flag:
        events.append({
            "name": "blackbox.candidate_triggers",
            "attributes": {"candidate_triggers": [t.model_dump(mode="json") for t in payload.candidate_triggers]},
        })
    return events
