"""
Abuse guardrails for the hosted demo (Section 8) — this is a public
endpoint hitting a paid model API. Everything here is app-level defense in
depth; the AWS deployment (M11) adds a WAF/ALB rate limit and a CloudWatch
billing alarm in front of this, neither of which this process can see or
control, which is exactly why app-level limits exist too — they're what
still holds if the infra-level ones are ever misconfigured or absent (as
they are, running locally, right now).
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict, deque

logger = logging.getLogger("blackbox.demo.guardrails")

# "No free-text prompt input in v1" (Section 8) is enforced by construction
# elsewhere — the API only ever accepts a scenario_id from a fixed set
# (scenarios/incidents/definitions.py), never an arbitrary task string.


class RateLimitExceeded(Exception):
    pass


class DemoRunLog:
    """Logs every demo run attempt with IP for abuse review (Section 8).
    Stdout/structured-log by design — a real deployment ships this to
    CloudWatch Logs; nothing here assumes a particular sink."""

    def log_attempt(self, *, ip: str, scenario_id: str, allowed: bool, reason: str = "") -> None:
        logger.info(
            "demo_run_attempt ip=%s scenario_id=%s allowed=%s%s",
            ip, scenario_id, allowed, f" reason={reason}" if reason else "",
        )


class IpRateLimiter:
    """Sliding-window limiter per IP, in-memory. Good enough for a single
    demo process; the ALB/WAF rate limit (Section 8, M11) is the layer
    that actually needs to survive multiple instances.

    `max_runs`/`window_seconds` default to `None` and are resolved from
    the environment inside __init__, not via a module-level constant used
    as a default parameter value — a default parameter is bound once at
    *function definition* time (import time), so an env var changed after
    import (the normal case in tests, and in any process that re-reads
    config) would otherwise be silently ignored."""

    def __init__(self, *, max_runs: int | None = None, window_seconds: int | None = None) -> None:
        self._max_runs = max_runs if max_runs is not None else int(os.environ.get("DEMO_RATE_LIMIT_MAX_RUNS", "5"))
        window_seconds = (
            window_seconds if window_seconds is not None
            else int(os.environ.get("DEMO_RATE_LIMIT_WINDOW_SECONDS", "3600"))
        )
        self._window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, ip: str) -> None:
        now = time.monotonic()
        hits = self._hits[ip]
        while hits and now - hits[0] > self._window_seconds:
            hits.popleft()
        if len(hits) >= self._max_runs:
            raise RateLimitExceeded(
                f"{ip} has run {len(hits)} demo scenarios in the last {self._window_seconds}s "
                f"(limit {self._max_runs})"
            )
        hits.append(now)


class KillSwitch:
    """The application-level end of Section 8's "CloudWatch billing alarm
    with an automated kill switch that disables live runs and falls back
    to recorded traces." In this build, EventBridge/Lambda (M11) would
    flip this env var (or, at the AWS layer, update a Parameter Store
    value this reads); the important part built here is that this process
    checks it before every live attempt, not after."""

    @staticmethod
    def live_runs_enabled() -> bool:
        return os.environ.get("DEMO_LIVE_RUNS_ENABLED", "true").lower() != "false"
