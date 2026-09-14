"""
Runs the detector stack over a trace (Section 6.4) and produces
`detection_flag` steps, each carrying a ranked candidate-trigger list
(I8). Runs on the trace stream, not in the mediator's request path — the
one exception, the inline baseline check the mediator does per tool call,
reads a cached baseline and never calls into this module directly.
"""

from __future__ import annotations

from typing import Any

from common.schema import CandidateTrigger, DetectionFlagPayload, Step, StepType, Trace

from .baseline import Baseline
from .detectors import (
    argument_anomaly,
    exfiltration_shape,
    injection_heuristic,
    policy_violation,
    post_stop_activity,
    sequence_anomaly,
    unknown_tool,
    untrusted_influence,
    volume_anomaly,
)
from .triggers import rank_candidate_triggers

# One entry per row of Section 6.4's detector table, in table order.
_DETECTORS = [
    unknown_tool,
    policy_violation,
    argument_anomaly,
    sequence_anomaly,
    volume_anomaly,
    untrusted_influence,
    injection_heuristic,
    exfiltration_shape,
    post_stop_activity,
]

def run_detectors(
    trace: Trace, *, agent_baseline: Baseline | None = None, human_baseline: Baseline | None = None,
    tool_registry: Any = None,
) -> list[Step]:
    """Returns new `detection_flag` Steps (not yet appended to the trace,
    sequence numbers continuing from where it left off) — one per proposed
    flag, each with a ranked candidate-trigger list attached.

    `tool_registry`, like the baselines, is passed uniformly to every
    detector even though only sequence_anomaly currently reads it (severity
    by destination-tool risk class) — duck-typed as anything with `.get(name)`
    returning an object with a `.risk`, so this module doesn't need to
    import mediator.execution.registry.ToolRegistry just for a type hint."""
    steps_by_id = {s.step_id: s for s in trace.steps}
    next_sequence = (max((s.sequence for s in trace.steps), default=-1)) + 1

    detection_steps: list[Step] = []
    for module in _DETECTORS:
        proposed = module.detect(
            trace, agent_baseline=agent_baseline, human_baseline=human_baseline, tool_registry=tool_registry,
        )
        for flag in proposed:
            flagged_step = steps_by_id[flag.flagged_step_id]
            triggers: list[CandidateTrigger] = rank_candidate_triggers(trace, flagged_step)
            step = Step(
                session_id=trace.session.session_id,
                sequence=next_sequence,
                type=StepType.detection_flag,
                parent_step_id=flag.flagged_step_id,
                payload=DetectionFlagPayload(
                    severity=flag.severity,
                    detector_id=flag.detector_id,
                    description=flag.description,
                    candidate_triggers=triggers,
                    baseline_ref=flag.baseline_ref,
                ),
            )
            next_sequence += 1
            detection_steps.append(step)
    return detection_steps
