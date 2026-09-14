"""`volume_anomaly` (Section 6.4, type: baseline). Call rate or count
outside the envelope. Checked against BOTH the agent baseline and,
separately, the human baseline (I7) — abuse mode specifically needs the
human comparison, since a human driving a legitimate agent through an
unusually large number of calls may look entirely normal against the
agent's own baseline (the agent is just doing what it's told)."""

from __future__ import annotations

from common.schema import StepType, Trace

from .base import ProposedFlag

_VOLUME_MULTIPLIER = 1.5


def _flag_for(trace: Trace, baseline, subject_label: str) -> list[ProposedFlag]:
    if baseline is None or baseline.calls_per_session_max <= 0:
        return []
    tool_request_steps = [s for s in trace.steps if s.type == StepType.tool_request]
    count = len(tool_request_steps)
    threshold = baseline.calls_per_session_max * _VOLUME_MULTIPLIER
    if count <= threshold or not tool_request_steps:
        return []
    last_step = tool_request_steps[-1]
    return [ProposedFlag(
        flagged_step_id=last_step.step_id,
        severity="high",
        detector_id="volume_anomaly",
        description=(
            f"{count} tool calls this session vs. a learned {subject_label} envelope of "
            f"{baseline.calls_per_session_max} (threshold {threshold:.0f})"
        ),
        baseline_ref=baseline.ref(),
    )]


def detect(trace: Trace, *, agent_baseline=None, human_baseline=None, tool_registry=None) -> list[ProposedFlag]:
    return _flag_for(trace, agent_baseline, "agent") + _flag_for(trace, human_baseline, "human")
