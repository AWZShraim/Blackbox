"""
Candidate trigger ranking (Section 6.4, I8). When a flag fires, walk
backward through the trace and score each prior piece of context for:

  - recency relative to the flagged step
  - trust level of the content introduced
  - whether the injection heuristic fired on that content
  - whether the flagged step's tool name/arguments appear textually in it
  - whether the step introduced new capability into the context

Returns a ranked list with a per-signal explanation. Never a single answer
— I8 exists specifically so this module cannot collapse into "return the
top candidate."
"""

from __future__ import annotations

from common.schema import CandidateTrigger, SourceType, Step, StepType, Trace, TrustLevel

from .detectors import injection_heuristic

MAX_CANDIDATES = 5


def _flagged_action_text(step: Step) -> str:
    if step.type == StepType.tool_request:
        return f"{step.payload.tool_name} {step.payload.arguments}"
    if step.type == StepType.model_response:
        calls = " ".join(f"{c.tool_name} {c.arguments}" for c in step.payload.tool_calls)
        return f"{step.payload.text or ''} {calls}"
    if step.type == StepType.model_call:
        return " ".join(seg.text for seg in step.payload.context_composition)
    return ""


def _textual_overlap(segment_text: str, flagged_text: str) -> bool:
    if not flagged_text.strip():
        return False
    words = {w.lower() for w in flagged_text.split() if len(w) > 4}
    segment_lower = segment_text.lower()
    return any(w in segment_lower for w in words)


def rank_candidate_triggers(trace: Trace, flagged_step: Step, *, max_candidates: int = MAX_CANDIDATES) -> list[CandidateTrigger]:
    flagged_idx = next((i for i, s in enumerate(trace.steps) if s.step_id == flagged_step.step_id), None)
    if flagged_idx is None:
        return []
    flagged_text = _flagged_action_text(flagged_step)

    candidates: list[CandidateTrigger] = []
    for i in range(flagged_idx, -1, -1):
        step = trace.steps[i]
        if step.type != StepType.model_call:
            continue
        for seg in step.payload.context_composition:
            signals: list[str] = []
            score = 0.0

            distance = max(flagged_idx - i, 0)
            recency = 1.0 / (1.0 + distance)
            score += recency * 0.2
            if distance == 0:
                signals.append("same_step_as_flag")

            if seg.provenance.trust_level == TrustLevel.untrusted:
                signals.append("untrusted_source")
                score += 0.3
            elif seg.provenance.trust_level == TrustLevel.semi_trusted:
                score += 0.05

            if injection_heuristic.fires(seg.text):
                signals.append("injection_heuristic_fired")
                score += 0.3

            if _textual_overlap(seg.text, flagged_text):
                signals.append("textual_overlap_with_flagged_action")
                score += 0.2

            if seg.provenance.source_type in (SourceType.tool_result, SourceType.sub_agent):
                signals.append("introduced_new_capability_into_context")
                score += 0.05

            if not signals:
                continue

            candidates.append(CandidateTrigger(
                step_id=step.step_id,
                content_id=seg.provenance.content_id,
                score=min(score, 1.0),
                reasoning=_reasoning(seg, signals),
                signals=signals,
            ))

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[:max_candidates]


def _reasoning(seg, signals: list[str]) -> str:
    source = seg.provenance.source_identifier or seg.provenance.source_type.value
    parts = []
    if "untrusted_source" in signals:
        parts.append(f"content from {source} is untrusted")
    if "injection_heuristic_fired" in signals:
        parts.append("contains instruction-like phrasing")
    if "textual_overlap_with_flagged_action" in signals:
        parts.append("shares vocabulary with the flagged action")
    if "introduced_new_capability_into_context" in signals:
        parts.append("was introduced by a prior tool result")
    return "; ".join(parts) if parts else f"content from {source} precedes the flagged step"
