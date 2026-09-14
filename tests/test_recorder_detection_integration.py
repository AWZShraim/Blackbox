"""
M8 groundwork: detection actually runs on the trace stream as steps land
at the recorder (Section 6.4), not just when a test calls
detector.engine.run_detectors directly against an already-complete trace.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from common.schema import Trace
from recorder.main import _process_event
from recorder.store.s3_archive import LocalDiskArchive

FIXTURE = Path(__file__).parent.parent / "scenarios" / "fixtures" / "fixture_reasoning_compromise.json"


@pytest.mark.asyncio
async def test_detection_flags_are_produced_as_steps_land_at_the_recorder(postgres_store, tmp_path):
    trace = Trace.model_validate(json.loads(FIXTURE.read_text()))
    archive = LocalDiskArchive(tmp_path / "archive")

    await _process_event(
        trace.session, store=postgres_store, archive=archive, exporters=[],
        baseline_store=None, run_detection=True,
    )
    for step in trace.steps:
        await _process_event(
            step, store=postgres_store, archive=archive, exporters=[],
            baseline_store=None, run_detection=True,
        )

    stored = await postgres_store.get_trace(trace.session.session_id)
    flag_steps = [s for s in stored.steps if s.type.value == "detection_flag"]
    detector_ids = {s.payload.detector_id for s in flag_steps}

    assert "injection_heuristic" in detector_ids
    assert "untrusted_influence" in detector_ids
    assert "exfiltration_shape" in detector_ids
    assert "policy_violation" in detector_ids

    # idempotent: replaying the same steps must not duplicate flags
    for step in trace.steps:
        await _process_event(
            step, store=postgres_store, archive=archive, exporters=[],
            baseline_store=None, run_detection=True,
        )
    stored_again = await postgres_store.get_trace(trace.session.session_id)
    flag_steps_again = [s for s in stored_again.steps if s.type.value == "detection_flag"]
    assert len(flag_steps_again) == len(flag_steps)


@pytest.mark.asyncio
async def test_clean_trace_produces_no_detection_flags_through_the_recorder(postgres_store, tmp_path):
    clean_fixture = Path(__file__).parent.parent / "scenarios" / "fixtures" / "clean_session.json"
    trace = Trace.model_validate(json.loads(clean_fixture.read_text()))
    archive = LocalDiskArchive(tmp_path / "archive")

    await _process_event(
        trace.session, store=postgres_store, archive=archive, exporters=[],
        baseline_store=None, run_detection=True,
    )
    for step in trace.steps:
        await _process_event(
            step, store=postgres_store, archive=archive, exporters=[],
            baseline_store=None, run_detection=True,
        )

    stored = await postgres_store.get_trace(trace.session.session_id)
    assert not any(s.type.value == "detection_flag" for s in stored.steps)
