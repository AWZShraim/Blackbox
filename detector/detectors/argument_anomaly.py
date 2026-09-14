"""`argument_anomaly` (Section 6.4, type: baseline). Argument outside the
learned shape — a numeric value outside the observed [min, max] envelope
(with a small tolerance margin so the first slightly-larger-than-usual
legitimate call doesn't flag), or a categorical value never seen before."""

from __future__ import annotations

from common.schema import StepType, Trace

from .base import ProposedFlag

# Numeric values within this margin above the learned max (or below the
# learned min) are still normal — real-world values drift a little.
_NUMERIC_TOLERANCE = 1.2


def detect(trace: Trace, *, agent_baseline=None, human_baseline=None) -> list[ProposedFlag]:
    if agent_baseline is None:
        return []
    flags: list[ProposedFlag] = []
    for step in trace.steps:
        if step.type != StepType.tool_request:
            continue
        tool_baseline = agent_baseline.tools.get(step.payload.tool_name)
        if tool_baseline is None:
            continue  # sequence_anomaly / unknown_tool cover "never seen this tool at all"
        for arg_name, arg_value in step.payload.arguments.items():
            shape = tool_baseline.argument_shapes.get(arg_name)
            if shape is None:
                continue
            if shape.is_numeric and isinstance(arg_value, (int, float)) and not isinstance(arg_value, bool):
                lo = (shape.min_value or 0) / _NUMERIC_TOLERANCE if shape.min_value else None
                hi = (shape.max_value or 0) * _NUMERIC_TOLERANCE if shape.max_value else None
                if (hi is not None and arg_value > hi) or (lo is not None and arg_value < lo):
                    flags.append(ProposedFlag(
                        flagged_step_id=step.step_id,
                        severity="high",
                        detector_id="argument_anomaly",
                        description=(
                            f"{step.payload.tool_name}({arg_name}={arg_value!r}) is outside the learned "
                            f"range [{shape.min_value}, {shape.max_value}]"
                        ),
                        baseline_ref=agent_baseline.ref(),
                    ))
            elif not shape.is_numeric and shape.seen_values and arg_value not in shape.seen_values:
                flags.append(ProposedFlag(
                    flagged_step_id=step.step_id,
                    severity="medium",
                    detector_id="argument_anomaly",
                    description=f"{step.payload.tool_name}({arg_name}={arg_value!r}) was never seen in the baseline",
                    baseline_ref=agent_baseline.ref(),
                ))
    return flags
