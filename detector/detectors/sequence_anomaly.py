"""`sequence_anomaly` (Section 6.4, type: baseline). Unseen tool transition
— a (prior_tool, tool) bigram never observed during baselining. Flags the
second call in the pair, since that is the one that deviates.

Two refinements on top of the bare "unseen bigram" check:

- Severity scales with the destination tool's risk class (`tool_registry`,
  duck-typed as anything with `.get(name)` returning an object with a
  `.risk`) — an unseen transition into a critical-risk tool is a materially
  different signal than one into a low-risk read, so it shouldn't carry the
  same flat severity.
- The detector stays silent on an immature baseline (Baseline.is_mature,
  detector/baseline.py): with too few learning-period sessions, "never
  observed" mostly means "not observed yet in this small a sample," not
  "abnormal."

`evaluate_transition` below is the shared core of both refinements plus the
unseen-pair test itself, with nothing in it about walking a trace or
deduping repeats. mediator.core.Mediator's synchronous `_inline_baseline_check`
calls it too (passing its cached last-tool-name and the mediator's own
`ToolRegistry`) so the live enforcement path and this offline/forensic path
can't independently drift on what counts as anomalous or how severe it is —
in a forensics tool, a live flag and a stored flag disagreeing about the
same transition is a correctness bug, not a cosmetic one."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from common.schema import Severity, StepType, Trace

from .base import ProposedFlag

if TYPE_CHECKING:
    from ..baseline import Baseline

_DEFAULT_SEVERITY = Severity.medium


def _severity_for(tool_name: str, tool_registry: Any) -> Severity:
    if tool_registry is not None:
        spec = tool_registry.get(tool_name)
        risk = getattr(spec, "risk", None)
        if risk is not None:
            return Severity(risk.value)
    return _DEFAULT_SEVERITY


def evaluate_transition(
    prior_tool: str, tool: str, *, agent_baseline: "Baseline", tool_registry: Any = None,
) -> tuple[Severity, str] | None:
    """Is `prior_tool -> tool` an unseen, baseline-eligible transition? If
    so, returns `(severity, description)`; otherwise None — either the
    transition is normal, one of the two tools isn't in the baseline's
    tool_set (so there's nothing to compare against), or the baseline isn't
    mature enough to trust its negative space yet."""
    if not agent_baseline.sequences or not agent_baseline.is_mature:
        return None
    if tool not in agent_baseline.tool_set or prior_tool not in agent_baseline.tool_set:
        return None
    if agent_baseline.has_sequence(prior_tool, tool):
        return None
    description = f"transition {prior_tool} -> {tool} was never observed in the baseline"
    return _severity_for(tool, tool_registry), description


def detect(
    trace: Trace, *, agent_baseline=None, human_baseline=None, tool_registry: Any = None,
) -> list[ProposedFlag]:
    if agent_baseline is None:
        return []

    flags: list[ProposedFlag] = []
    # One flag per distinct (prior_tool, name) pair per session — the same
    # unseen transition recurring later in the trace is the same behavioural
    # deviation, not a new one, so it shouldn't multiply the alert count.
    flagged_pairs: set[tuple[str, str]] = set()
    prior_tool: str | None = None
    for step in trace.steps:
        if step.type != StepType.tool_request:
            continue
        name = step.payload.tool_name
        if prior_tool is not None:
            pair = (prior_tool, name)
            if pair not in flagged_pairs:
                result = evaluate_transition(
                    prior_tool, name, agent_baseline=agent_baseline, tool_registry=tool_registry,
                )
                if result is not None:
                    severity, description = result
                    flagged_pairs.add(pair)
                    flags.append(ProposedFlag(
                        flagged_step_id=step.step_id,
                        severity=severity,
                        detector_id="sequence_anomaly",
                        description=description,
                        baseline_ref=agent_baseline.ref(),
                    ))
        prior_tool = name
    return flags
