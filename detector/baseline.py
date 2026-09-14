"""
Baseline model (Section 6.4): the learned envelope of normal behaviour for
a given agent, and separately per human (I7) — this is what makes abuse-mode
detection possible, since a human driving a legitimate agent toward
excessive-agency behaviour won't look anomalous against the AGENT's
baseline alone.

Learned during an observe-only period. Stored as versioned, inspectable,
human-editable JSON — a platform engineer must be able to review and
correct a proposed baseline before enforcement is enabled (this module
only ever *proposes*; nothing here flips an enforcement switch).
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from common.schema import StepType, Trace


class ArgumentShape(BaseModel):
    """Learned shape for one tool argument. Numeric args get a [min, max]
    envelope; everything else gets a capped sample of values actually
    seen, treated as a closed set."""

    is_numeric: bool = False
    min_value: float | None = None
    max_value: float | None = None
    seen_values: list[Any] = Field(default_factory=list)


class ToolBaseline(BaseModel):
    call_count: int = 0
    argument_shapes: dict[str, ArgumentShape] = Field(default_factory=dict)


class Baseline(BaseModel):
    subject_type: str  # "agent" | "human"
    subject_id: str
    version: int = 1
    learned_at: str
    sessions_observed: int = 0
    tool_set: list[str] = Field(default_factory=list)
    tools: dict[str, ToolBaseline] = Field(default_factory=dict)
    # Observed (prior_tool, tool) bigrams, sorted for stable diffs when a
    # human hand-edits the file.
    sequences: list[list[str]] = Field(default_factory=list)
    calls_per_session_max: int = 0
    provenance_trust_ratio: dict[str, float] = Field(default_factory=dict)

    def ref(self) -> str:
        return f"baseline:{self.subject_type}:{self.subject_id}:v{self.version}"

    def has_sequence(self, prior_tool: str, tool: str) -> bool:
        return [prior_tool, tool] in self.sequences


class BaselineStore:
    """Versioned, inspectable, human-editable JSON files on disk — one per
    subject, openable and hand-correctable before enforcement is enabled."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, subject_type: str, subject_id: str) -> Path:
        safe_id = subject_id.replace("/", "_").replace(":", "_")
        return self._root / f"{subject_type}-{safe_id}.json"

    def save(self, baseline: Baseline) -> Path:
        path = self._path(baseline.subject_type, baseline.subject_id)
        path.write_text(baseline.model_dump_json(indent=2))
        return path

    def load(self, subject_type: str, subject_id: str) -> Baseline | None:
        path = self._path(subject_type, subject_id)
        if not path.exists():
            return None
        return Baseline.model_validate_json(path.read_text())


def learn_baseline(*, subject_type: str, subject_id: str, traces: list[Trace]) -> Baseline:
    """One observe-only learning pass over every trace belonging to one
    subject (an agent_id, or — for abuse-mode baselining — a human_id)."""
    tools: dict[str, ToolBaseline] = {}
    sequences: set[tuple[str, str]] = set()
    calls_per_session_max = 0
    trust_counts: Counter[str] = Counter()

    for trace in traces:
        prior_tool: str | None = None
        session_call_count = 0
        for step in trace.steps:
            if step.type == StepType.tool_request:
                session_call_count += 1
                name = step.payload.tool_name
                tb = tools.setdefault(name, ToolBaseline())
                tb.call_count += 1
                for arg_name, arg_value in step.payload.arguments.items():
                    shape = tb.argument_shapes.setdefault(arg_name, ArgumentShape())
                    if isinstance(arg_value, (int, float)) and not isinstance(arg_value, bool):
                        shape.is_numeric = True
                        shape.min_value = arg_value if shape.min_value is None else min(shape.min_value, arg_value)
                        shape.max_value = arg_value if shape.max_value is None else max(shape.max_value, arg_value)
                    elif len(shape.seen_values) < 50 and arg_value not in shape.seen_values:
                        shape.seen_values.append(arg_value)
                if prior_tool is not None:
                    sequences.add((prior_tool, name))
                prior_tool = name
            elif step.type == StepType.model_call:
                for seg in step.payload.context_composition:
                    trust_counts[seg.provenance.trust_level.value] += 1
        calls_per_session_max = max(calls_per_session_max, session_call_count)

    total_trust = sum(trust_counts.values()) or 1
    trust_ratio = {k: v / total_trust for k, v in trust_counts.items()}

    return Baseline(
        subject_type=subject_type,
        subject_id=subject_id,
        learned_at=datetime.now(timezone.utc).isoformat(),
        sessions_observed=len(traces),
        tool_set=sorted(tools.keys()),
        tools=tools,
        sequences=sorted([list(pair) for pair in sequences]),
        calls_per_session_max=calls_per_session_max,
        provenance_trust_ratio=trust_ratio,
    )
