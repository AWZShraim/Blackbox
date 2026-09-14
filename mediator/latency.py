"""
Tracks policy + baseline evaluation latency — the budget from Section 6.2:
"policy evaluation plus baseline check must add under 10ms p99, excluding
actual tool execution." A bounded in-memory reservoir; this only needs to
answer "are we under budget," not survive a restart.
"""

from __future__ import annotations


class LatencyTracker:
    def __init__(self, *, max_samples: int = 5000) -> None:
        self._samples: list[float] = []
        self._max_samples = max_samples

    def record(self, elapsed_ms: float) -> None:
        self._samples.append(elapsed_ms)
        if len(self._samples) > self._max_samples:
            self._samples.pop(0)

    def percentile(self, p: float) -> float | None:
        if not self._samples:
            return None
        ordered = sorted(self._samples)
        idx = min(int(len(ordered) * p), len(ordered) - 1)
        return ordered[idx]

    @property
    def p50(self) -> float | None:
        return self.percentile(0.50)

    @property
    def p99(self) -> float | None:
        return self.percentile(0.99)

    @property
    def count(self) -> int:
        return len(self._samples)
