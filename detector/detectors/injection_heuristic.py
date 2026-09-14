"""
`injection_heuristic` (Section 6.4, type: content). Imperative patterns in
UNTRUSTED content only: instruction-like phrasing, role redefinition,
exfiltration verbs. This is a heuristic, not a classifier — it is honest
about that (I8): it contributes a signal to candidate-trigger ranking, it
never claims to have detected intent.

Exposed as a standalone `fires`/`score` pair so detector/triggers.py can
reuse the exact same heuristic when scoring candidate triggers, rather than
two subtly different implementations drifting apart.
"""

from __future__ import annotations

import re

from common.schema import Step, StepType, Trace, TrustLevel

from .base import ProposedFlag

# Deliberately conservative and explainable — every pattern here is one a
# human reviewing a flag can read and immediately understand why it fired.
_INSTRUCTION_PATTERNS = [
    r"\bsystem\s*(notice|note|message)\b",
    r"\bmandatory\b",
    r"\bmust\s+be\s+(done|sent|exported|issued)\b",
    r"\bdo\s+not\s+(flag|review|notify|ask)\b",
    r"\bwithout\s+(additional\s+)?(confirmation|approval|review)\b",
    r"\bbefore\s+(any\s+)?repl(y|ying)\b",
    r"\bimmediately\b",
    r"\boverride\b",
    r"\bignore\s+(the\s+)?(previous|prior|above)\b",
    r"\byou\s+are\s+now\b",
    r"\bnew\s+instructions?\b",
]
_EXFIL_VERB_PATTERNS = [
    r"\bexport\b",
    r"\bsend\b.{0,40}\b(email|attachment|to)\b",
    r"\bforward\b.{0,40}\bto\b",
    r"\bemail\b.{0,40}\b(record|data|customer|account)s?\b",
]

_ALL_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _INSTRUCTION_PATTERNS + _EXFIL_VERB_PATTERNS]


def matched_patterns(text: str) -> list[str]:
    return [p.pattern for p in _ALL_PATTERNS if p.search(text)]


def fires(text: str) -> bool:
    return len(matched_patterns(text)) > 0


def detect(trace: Trace, *, agent_baseline=None, human_baseline=None) -> list[ProposedFlag]:
    flags: list[ProposedFlag] = []
    for step in trace.steps:
        if step.type != StepType.model_call:
            continue
        for seg in step.payload.context_composition:
            if seg.provenance.trust_level != TrustLevel.untrusted:
                continue  # trusted/semi-trusted content issuing imperatives isn't the signal this detector is for
            hits = matched_patterns(seg.text)
            if hits:
                flags.append(ProposedFlag(
                    flagged_step_id=step.step_id,
                    severity="medium",
                    detector_id="injection_heuristic",
                    description=(
                        f"untrusted content from {seg.provenance.source_type.value} "
                        f"({seg.provenance.source_identifier or 'unknown'}) contains "
                        f"instruction-like phrasing: {', '.join(hits[:3])}"
                    ),
                ))
    return flags
