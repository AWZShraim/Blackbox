"""`sequence_anomaly` (Section 6.4, type: baseline). Unseen tool transition
— a (prior_tool, tool) bigram never observed during baselining. Flags the
second call in the pair, since that is the one that deviates."""

from __future__ import annotations

from common.schema import StepType, Trace

from .base import ProposedFlag


def detect(trace: Trace, *, agent_baseline=None, human_baseline=None) -> list[ProposedFlag]:
    if agent_baseline is None or not agent_baseline.sequences:
        return []
    flags: list[ProposedFlag] = []
    prior_tool: str | None = None
    for step in trace.steps:
        if step.type != StepType.tool_request:
            continue
        name = step.payload.tool_name
        if prior_tool is not None and name in agent_baseline.tool_set and prior_tool in agent_baseline.tool_set:
            if not agent_baseline.has_sequence(prior_tool, name):
                flags.append(ProposedFlag(
                    flagged_step_id=step.step_id,
                    severity="medium",
                    detector_id="sequence_anomaly",
                    description=f"transition {prior_tool} -> {name} was never observed in the baseline",
                    baseline_ref=agent_baseline.ref(),
                ))
        prior_tool = name
    return flags
