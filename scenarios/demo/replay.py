"""
Replay: reads a stored trace and emits its events over the same channel a
live run uses, with synthetic timing (I9, Section 8's fallback path). This
is what "serve the most recent successful trace... with a small notice"
actually does under the hood — the visitor's browser never learns the
difference, because architecturally there isn't one: this just POSTs to
the same /sessions and /sessions/{id}/steps endpoints the mediator uses.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import timedelta

import httpx

from common.schema import Session, SessionStatus, Step, Trace, utcnow

logger = logging.getLogger("blackbox.demo.replay")

# Keep a replay watchable in one sitting regardless of how long the
# original run actually took.
MAX_REPLAY_SECONDS = 25.0
MIN_STEP_GAP_SECONDS = 0.15


def _scaled_gaps(steps: list[Step]) -> list[float]:
    if len(steps) <= 1:
        return [0.0] * len(steps)
    raw_gaps = [0.0]
    for prev, cur in zip(steps, steps[1:]):
        raw_gaps.append(max((cur.started_at - prev.started_at).total_seconds(), 0.0))
    total = sum(raw_gaps)
    if total <= 0:
        return [MIN_STEP_GAP_SECONDS] * len(steps)
    scale = min(1.0, MAX_REPLAY_SECONDS / total)
    return [max(g * scale, MIN_STEP_GAP_SECONDS if g > 0 else 0.0) for g in raw_gaps]


async def replay_trace(
    source: Trace, *, recorder_url: str, scenario_id: str | None = None,
) -> uuid.UUID:
    """Fire-and-forget: call as `asyncio.create_task(replay_trace(...))`.
    Returns the new session_id immediately (before any events are sent) so
    the caller can hand it to the frontend right away and let the SSE
    stream carry the rest — same "stream steps as they occur" experience
    as a live run (Section 8)."""
    new_session_id = uuid.uuid4()
    id_map = {source.session.session_id: new_session_id}
    started_at = utcnow()

    new_session = source.session.model_copy(update={
        "session_id": new_session_id,
        "started_at": started_at,
        "ended_at": None,
        "status": SessionStatus.running,
        "scenario_id": scenario_id or source.session.scenario_id,
    })

    async def _run() -> None:
        async with httpx.AsyncClient(base_url=recorder_url, timeout=10.0) as http:
            await http.post(
                "/sessions", content=new_session.model_dump_json(), headers={"content-type": "application/json"}
            )

            gaps = _scaled_gaps(source.steps)
            elapsed = timedelta()
            for step, gap in zip(source.steps, gaps):
                await asyncio.sleep(gap)
                elapsed += timedelta(seconds=gap)
                remapped = step.model_copy(update={
                    "session_id": new_session_id,
                    "step_id": uuid.uuid4(),
                    "started_at": started_at + elapsed,
                    "parent_step_id": id_map.get(step.parent_step_id, step.parent_step_id),
                })
                # tool_request steps carry `requested_by` as another
                # step_id — leave it pointing at the ORIGINAL id map entry
                # if we've seen it, otherwise leave as-is (best effort;
                # cosmetic only, not load-bearing for the replay).
                try:
                    resp = await http.post(
                        f"/sessions/{new_session_id}/steps", content=remapped.model_dump_json(),
                        headers={"content-type": "application/json"},
                    )
                    resp.raise_for_status()
                except httpx.HTTPError:
                    logger.exception("blackbox demo: failed to replay a step")

            final_status = source.session.status
            if final_status not in (SessionStatus.completed, SessionStatus.failed, SessionStatus.terminated):
                final_status = SessionStatus.completed
            finished_session = new_session.model_copy(update={
                "status": final_status, "ended_at": started_at + elapsed,
            })
            await http.post(
                "/sessions", content=finished_session.model_dump_json(), headers={"content-type": "application/json"}
            )

    asyncio.create_task(_run())
    return new_session_id
