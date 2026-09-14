"""`unknown_tool` (Section 6.4, type: policy). Tool not in registered
catalogue — the mediator already refuses to execute it (Section 6.2 step
2); this detector makes that refusal visible as a first-class flag in the
trace rather than something only findable by reading policy_decision
payloads one at a time."""

from __future__ import annotations

from common.schema import StepType, Trace

from .base import ProposedFlag


def detect(trace: Trace, *, agent_baseline=None, human_baseline=None) -> list[ProposedFlag]:
    flags: list[ProposedFlag] = []
    for step in trace.steps:
        if step.type != StepType.policy_decision:
            continue
        if step.payload.rule_matched == "deny_unknown_tool":
            flags.append(ProposedFlag(
                flagged_step_id=step.step_id,
                severity="high",
                detector_id="unknown_tool",
                description=f"tool call rejected: {step.payload.reason}",
            ))
    return flags
