"""The demo's agent baseline must actually be usable — mature enough
(detector.baseline.MIN_SESSIONS_FOR_MATURITY) that sequence_anomaly and the
mediator's inline_sequence_anomaly check don't silently suppress every flag
throughout a live demo run, and both create_app()s must fail loudly at
startup rather than silently accepting a too-thin one."""

from __future__ import annotations

import pytest

from detector.baseline import (
    MIN_SESSIONS_FOR_MATURITY,
    Baseline,
    BaselineStore,
    raise_if_immature,
)
from recorder.store.s3_archive import LocalDiskArchive
from scenarios.demo.seed_baseline import seed_baseline


def test_seed_baseline_produces_a_mature_agent_baseline(tmp_path):
    seed_baseline(tmp_path)
    baseline = BaselineStore(tmp_path).load("agent", "support-agent")
    assert baseline is not None
    assert baseline.is_mature
    assert baseline.sessions_observed >= MIN_SESSIONS_FOR_MATURITY


def test_raise_if_immature_fails_loudly_on_a_thin_baseline():
    thin = Baseline(
        subject_type="agent", subject_id="support-agent", learned_at="2026-01-01T00:00:00Z",
        sessions_observed=MIN_SESSIONS_FOR_MATURITY - 1,
    )
    with pytest.raises(RuntimeError, match="sessions_observed"):
        raise_if_immature(thin, source="test")


def test_raise_if_immature_accepts_a_mature_baseline():
    mature = Baseline(
        subject_type="agent", subject_id="support-agent", learned_at="2026-01-01T00:00:00Z",
        sessions_observed=MIN_SESSIONS_FOR_MATURITY,
    )
    raise_if_immature(mature, source="test")  # must not raise


def test_recorder_create_app_fails_loudly_on_a_thin_baseline_dir(postgres_dsn, tmp_path, monkeypatch):
    from recorder.main import create_app
    from recorder.store.postgres import PostgresStore

    thin = Baseline(
        subject_type="agent", subject_id="support-agent", learned_at="2026-01-01T00:00:00Z",
        sessions_observed=MIN_SESSIONS_FOR_MATURITY - 1,
    )
    BaselineStore(tmp_path).save(thin)
    monkeypatch.setenv("BLACKBOX_BASELINE_DIR", str(tmp_path))

    with pytest.raises(RuntimeError, match="sessions_observed"):
        create_app(
            store=PostgresStore(postgres_dsn),
            archive=LocalDiskArchive(tmp_path / "archive"),
            exporters=[],
        )


def test_recorder_create_app_accepts_the_seeded_demo_baseline_dir(postgres_dsn, tmp_path, monkeypatch):
    from recorder.main import create_app
    from recorder.store.postgres import PostgresStore

    seed_baseline(tmp_path)
    monkeypatch.setenv("BLACKBOX_BASELINE_DIR", str(tmp_path))

    create_app(  # must not raise
        store=PostgresStore(postgres_dsn),
        archive=LocalDiskArchive(tmp_path / "archive"),
        exporters=[],
    )
