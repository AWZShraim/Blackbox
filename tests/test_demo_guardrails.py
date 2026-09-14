"""M11: the kill switch's SSM path (deploy/terraform/modules/alerting's
Lambda flips this parameter when the budget alarm fires)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from scenarios.demo.guardrails import IpRateLimiter, KillSwitch, RateLimitExceeded


def test_kill_switch_defaults_to_env_var_when_no_ssm_param_configured(monkeypatch):
    monkeypatch.delenv("BLACKBOX_KILL_SWITCH_SSM_PARAM", raising=False)
    monkeypatch.setenv("DEMO_LIVE_RUNS_ENABLED", "false")
    assert KillSwitch.live_runs_enabled() is False
    monkeypatch.setenv("DEMO_LIVE_RUNS_ENABLED", "true")
    assert KillSwitch.live_runs_enabled() is True


def test_kill_switch_reads_ssm_when_configured(monkeypatch):
    KillSwitch._cache = None
    monkeypatch.setenv("BLACKBOX_KILL_SWITCH_SSM_PARAM", "/blackbox/demo/live_runs_enabled")

    mock_client = MagicMock()
    mock_client.get_parameter.return_value = {"Parameter": {"Value": "false"}}

    with patch("boto3.client", return_value=mock_client):
        assert KillSwitch.live_runs_enabled() is False

    mock_client.get_parameter.assert_called_once_with(Name="/blackbox/demo/live_runs_enabled")
    KillSwitch._cache = None


def test_kill_switch_fails_open_if_ssm_unreachable(monkeypatch):
    KillSwitch._cache = None
    monkeypatch.setenv("BLACKBOX_KILL_SWITCH_SSM_PARAM", "/blackbox/demo/live_runs_enabled")

    with patch("boto3.client", side_effect=RuntimeError("no network")):
        assert KillSwitch.live_runs_enabled() is True  # fail toward "keep the demo running"

    KillSwitch._cache = None


def test_rate_limiter_reads_env_var_at_construction_not_import_time(monkeypatch):
    """Regression for the M10 bug: a module-level default parameter value
    silently ignored env var changes made after import."""
    monkeypatch.setenv("DEMO_RATE_LIMIT_MAX_RUNS", "1")
    limiter = IpRateLimiter()
    limiter.check("1.2.3.4")
    with pytest.raises(RateLimitExceeded):
        limiter.check("1.2.3.4")
