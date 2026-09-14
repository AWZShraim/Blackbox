"""Shared shapes for every detector module. A detector is a plain function
`detect(trace, *, agent_baseline, human_baseline) -> list[ProposedFlag]` —
no base class, no registration ceremony, just a predictable signature that
detector/engine.py calls uniformly. Kept this simple deliberately: each
detector file in this package is independently testable against a fixture
trace with nothing else running."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from common.schema import Severity


@dataclass
class ProposedFlag:
    flagged_step_id: uuid.UUID
    severity: Severity
    detector_id: str
    description: str
    baseline_ref: str | None = None
