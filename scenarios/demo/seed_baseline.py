"""
Seeds the demo's agent baseline (Section 6.4) — the learned envelope of
"normal" tool sequences that detector.detectors.sequence_anomaly and the
mediator's inline_sequence_anomaly check (mediator/core.py) compare live and
recorded traffic against. Without this, both are permanently a no-op in the
demo: baselines are opt-in (mediator/main.py, recorder/main.py only load one
if BLACKBOX_BASELINE_DIR is set), and even a loaded-but-thin one is silently
suppressed by detector.baseline.Baseline.is_mature.

Learned from scenarios/fixtures/clean_session.json — the one hand-written
trace in this repo that represents ordinary, non-incident agent behaviour
(the incident fixtures are deliberately anomalous; learning from them would
bake the planted deviation itself into "normal") — repeated enough times to
comfortably clear MIN_SESSIONS_FOR_MATURITY. A real deployment would learn
this from an actual observe-only period (Section 6.4) instead of a repeated
fixture; the demo has no such period to observe, so this is the honest
substitute, and it means the seeded baseline only covers the two tools that
one clean trace exercises (get_ticket, update_ticket) — sequence_anomaly
correctly stays silent on every other tool, which is unseen-baseline
behaviour by design (detect() only compares tools both present in
tool_set), not a gap this script tries to paper over.

Run: `python -m scenarios.demo.seed_baseline` (wired to `make seed`, same as
scenarios.company.seed).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from common.schema import Trace
from detector.baseline import MIN_SESSIONS_FOR_MATURITY, BaselineStore, learn_baseline

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
DEFAULT_BASELINE_DIR = Path(__file__).parent / ".baselines"

# Comfortably over the maturity floor rather than sitting exactly on it, so
# a later bump to MIN_SESSIONS_FOR_MATURITY doesn't silently flip this back
# to immature.
SEED_SESSION_COUNT = 30


def seed_baseline(baseline_dir: Path | None = None) -> None:
    baseline_dir = baseline_dir or Path(os.environ.get("BLACKBOX_BASELINE_DIR", DEFAULT_BASELINE_DIR))
    trace = Trace.model_validate(json.loads((FIXTURES_DIR / "clean_session.json").read_text()))

    baseline = learn_baseline(
        subject_type="agent", subject_id="support-agent", traces=[trace] * SEED_SESSION_COUNT,
    )
    if not baseline.is_mature:
        raise RuntimeError(
            f"seeded demo baseline has sessions_observed={baseline.sessions_observed}, "
            f"below MIN_SESSIONS_FOR_MATURITY={MIN_SESSIONS_FOR_MATURITY} — "
            "raise SEED_SESSION_COUNT in scenarios/demo/seed_baseline.py"
        )

    path = BaselineStore(baseline_dir).save(baseline)
    print(
        f"seeded demo agent baseline at {path} "
        f"(sessions_observed={baseline.sessions_observed}, tool_set={baseline.tool_set})"
    )


if __name__ == "__main__":
    seed_baseline()
