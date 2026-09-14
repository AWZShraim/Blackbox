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
    to recorded traces." Locally, DEMO_LIVE_RUNS_ENABLED is a plain env
    var. In the AWS deployment (M11, deploy/terraform/modules/alerting), a
    Lambda subscribed to the budget-alarm SNS topic flips an SSM Parameter
    Store value instead — an env var can't be changed on a running ECS
    task without a new deployment, but a parameter this process polls can
    take effect within one cache TTL, no redeploy needed. Set
    BLACKBOX_KILL_SWITCH_SSM_PARAM to opt into that path; unset (the local
    default) means only the env var is consulted."""

    _cache: tuple[float, bool] | None = None
    _CACHE_TTL_SECONDS = 30.0

    @staticmethod
    def live_runs_enabled() -> bool:
        param_name = os.environ.get("BLACKBOX_KILL_SWITCH_SSM_PARAM")
        if not param_name:
            return os.environ.get("DEMO_LIVE_RUNS_ENABLED", "true").lower() != "false"

        now = time.monotonic()
        if KillSwitch._cache is not None and now - KillSwitch._cache[0] < KillSwitch._CACHE_TTL_SECONDS:
            return KillSwitch._cache[1]

        enabled = True
        try:
            import boto3

            ssm = boto3.client("ssm")
            value = ssm.get_parameter(Name=param_name)["Parameter"]["Value"]
            enabled = value.lower() != "false"
        except Exception:  # noqa: BLE001 - SSM unreachable must fail toward "keep the demo running," not a 500
            logger.exception("blackbox demo: could not read kill switch from SSM, defaulting to enabled")
            enabled = True

        KillSwitch._cache = (now, enabled)
        return enabled
