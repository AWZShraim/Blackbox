"""`untrusted_influence` (Section 6.4, type: provenance). Untrusted content
entered context, then behaviour deviated within N steps.

Distinct from injection_heuristic.py: that detector flags suspicious
CONTENT on its own. This one only fires when such content is *followed* by
actual tool activity within a short window — content plus consequence,
not content alone. That distinction is also what keeps this detector quiet
on the clean fixture: an untrusted-but-benign ticket body followed by a
routine tool call must not flag (Section 13's M7 acceptance: no flags on
the clean trace)."""

from __future__ import annotations

from common.schema import StepType, Trace, TrustLevel

from . import injection_heuristic
from .base import ProposedFlag

_WINDOW_STEPS = 4


def detect(trace: Trace, *, agent_baseline=None, human_baseline=None, tool_registry=None) -> list[ProposedFlag]:
    flags: list[ProposedFlag] = []
    for i, step in enumerate(trace.steps):
        if step.type != StepType.model_call:
            continue
        suspicious_segments = [
            seg for seg in step.payload.context_composition
            if seg.provenance.trust_level == TrustLevel.untrusted and injection_heuristic.fires(seg.text)
        ]
        if not suspicious_segments:
            continue

        window = trace.steps[i + 1 : i + 1 + _WINDOW_STEPS]
        deviating_step = next((s for s in window if s.type == StepType.tool_request), None)
        if deviating_step is None:
            continue

        seg = suspicious_segments[0]
        flags.append(ProposedFlag(
            flagged_step_id=step.step_id,
            severity="critical",
            detector_id="untrusted_influence",
            description=(
                f"untrusted content from {seg.provenance.source_identifier or seg.provenance.source_type.value} "
                f"with instruction-like phrasing was followed within {_WINDOW_STEPS} steps by "
                f"{deviating_step.payload.tool_name}(...)"
            ),
        ))
    return flags
