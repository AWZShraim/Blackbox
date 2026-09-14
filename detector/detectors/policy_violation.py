"""`policy_violation` (Section 6.4, type: policy). Explicit rule matched —
any non-allow policy decision other than the catalogue-membership case,
which unknown_tool.py already covers on its own."""

from __future__ import annotations

from common.schema import PolicyDecision, StepType, Trace

from .base import ProposedFlag

_SEVERITY_BY_DECISION = {
    PolicyDecision.deny: "high",
    PolicyDecision.require_approval: "medium",
}


def detect(trace: Trace, *, agent_baseline=None, human_baseline=None) -> list[ProposedFlag]:
    flags: list[ProposedFlag] = []
    for step in trace.steps:
        if step.type != StepType.policy_decision:
            continue
        payload = step.payload
        if payload.decision == PolicyDecision.allow:
            continue
        if payload.rule_matched == "deny_unknown_tool":
            continue  # unknown_tool.py's territory
        flags.append(ProposedFlag(
            flagged_step_id=step.step_id,
            severity=_SEVERITY_BY_DECISION.get(payload.decision, "medium"),
            detector_id="policy_violation",
            description=f"policy {payload.policy_id!r} rule {payload.rule_matched!r}: {payload.reason}",
        ))
    return flags
