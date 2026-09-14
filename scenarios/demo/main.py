"""
The hosted demo's orchestration layer (Section 8) — a primary deliverable,
not a nice-to-have. A visitor picks a scenario_id from a fixed set (no
free-text prompt input, ever) and gets a session_id back immediately, so
the Investigator can start streaming before the agent has even taken its
first turn ("streaming makes the wait the demo").

What happens after that session_id is issued is this module's job:
re-seed the scenario database (a stale "already resolved" ticket silently
defeats the whole demo — this exact failure mode is why, see M8's commit),
run the live agent with a timeout, and if it errors, times out, or simply
doesn't demonstrate anything (Section 8's "the agent simply behaves
correctly"), fall back to the most recent trace that DID — live-first,
graceful degradation, I9.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from common.schema import Trace
from scenarios.agent.loop import run_agent
from scenarios.agent.transport_mediated import MediatedTransport, establish_session, record_lifecycle_event
from scenarios.company.db import db_path as northwind_db_path
from scenarios.company.seed import seed
from scenarios.demo.guardrails import DemoRunLog, IpRateLimiter, KillSwitch, RateLimitExceeded
from scenarios.demo.replay import replay_trace
from scenarios.incidents.definitions import SCENARIOS, ScenarioDefinition
from scenarios.tools.definitions import build_registry

load_dotenv()
logger = logging.getLogger("blackbox.demo")

LIVE_RUN_TIMEOUT_SECONDS = float(os.environ.get("DEMO_LIVE_RUN_TIMEOUT_SECONDS", "45"))
DEMO_MODEL = os.environ.get("DEMO_MODEL", "claude-haiku-4-5-20251001")
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

# How long to give the recorder's async detection pipeline to catch up
# with the last step of a just-finished live run before deciding whether
# it demonstrated anything.
DETECTION_SETTLE_TIMEOUT_SECONDS = 5.0
DETECTION_SETTLE_POLL_SECONDS = 0.3


class RunRequest(BaseModel):
    scenario_id: str


class RunResponse(BaseModel):
    session_id: str
    mode: str  # "live" | "recorded"
    notice: str | None = None


class OutcomeResponse(BaseModel):
    status: str  # "pending" | "demonstrated" | "fallback"
    fallback_session_id: str | None = None


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _load_fixture_trace(filename: str) -> Trace:
    import json

    return Trace.model_validate(json.loads((FIXTURES_DIR / filename).read_text()))


async def _find_fallback_trace(scenario: ScenarioDefinition, *, recorder_url: str, exclude_session_id: str) -> Trace:
    """The most recent PAST live run for this scenario that actually
    demonstrated something, else the bootstrap fixture (Section 8: "serve
    the most recent successful trace... with a small notice")."""
    async with httpx.AsyncClient(base_url=recorder_url, timeout=10.0) as http:
        try:
            resp = await http.get("/sessions", params={"scenario_id": scenario.scenario_id, "limit": 20})
            resp.raise_for_status()
            candidates = resp.json()
        except httpx.HTTPError:
            candidates = []

        for candidate in candidates:
            if candidate["session_id"] == exclude_session_id:
                continue
            if candidate["status"] not in ("completed", "failed"):
                continue
            trace_resp = await http.get(f"/sessions/{candidate['session_id']}")
            if trace_resp.status_code != 200:
                continue
            trace = Trace.model_validate(trace_resp.json())
            if any(s.type.value == "detection_flag" for s in trace.steps):
                return trace

    if scenario.recorded_fixture is None:
        raise RuntimeError(f"no fallback trace available for scenario {scenario.scenario_id!r}")
    return _load_fixture_trace(scenario.recorded_fixture)


def create_app() -> FastAPI:
    mediator_url = os.environ.get("MEDIATOR_URL", os.environ.get("MEDIATOR_BASE_URL", "http://localhost:8000"))
    recorder_url = os.environ.get("RECORDER_URL", "http://localhost:8010")
    client_id = os.environ.get("MEDIATOR_CLIENT_ID", "demo-agent")
    client_secret = os.environ.get("MEDIATOR_CLIENT_SECRET", "demo-secret-change-me")

    rate_limiter = IpRateLimiter()
    run_log = DemoRunLog()
    outcomes: dict[str, dict] = {}

    async def _run_live_agent(session_id: str, session_token: str, scenario: ScenarioDefinition) -> None:
        outcomes[session_id] = {"status": "pending"}
        errored = False
        try:
            registry = build_registry()
            async with MediatedTransport(base_url=mediator_url, session_token=session_token, model=DEMO_MODEL) as transport:
                result = await asyncio.wait_for(
                    run_agent(transport, task_description=scenario.task_description, tool_schemas=registry.schemas_for_agent()),
                    timeout=LIVE_RUN_TIMEOUT_SECONDS,
                )
            await record_lifecycle_event(
                base_url=mediator_url, session_token=session_token, session_id=session_id,
                event="completed" if result.stop_reason == "end_turn" else "failed",
            )
        except Exception:  # noqa: BLE001 - any live-run failure triggers fallback, not a 500 to the visitor
            logger.exception("blackbox demo: live run failed for scenario %s", scenario.scenario_id)
            errored = True
            try:
                await record_lifecycle_event(
                    base_url=mediator_url, session_token=session_token, session_id=session_id,
                    event="failed", reason="live run errored or timed out",
                )
            except Exception:  # noqa: BLE001
                pass

        demonstrated = False
        if not errored:
            # Detection runs asynchronously in the recorder's own queue
            # (Section 6.4) — the agent finishing does not mean the
            # recorder has caught up yet. Poll briefly rather than
            # checking once immediately, which would race the drain loop
            # and misreport a real detection as "not demonstrated."
            try:
                async with httpx.AsyncClient(base_url=recorder_url, timeout=10.0) as http:
                    for _ in range(int(DETECTION_SETTLE_TIMEOUT_SECONDS / DETECTION_SETTLE_POLL_SECONDS)):
                        resp = await http.get(f"/sessions/{session_id}")
                        if resp.status_code == 200:
                            trace = Trace.model_validate(resp.json())
                            demonstrated = any(s.type.value == "detection_flag" for s in trace.steps)
                            if demonstrated:
                                break
                        await asyncio.sleep(DETECTION_SETTLE_POLL_SECONDS)
            except httpx.HTTPError:
                demonstrated = False

        if demonstrated:
            outcomes[session_id] = {"status": "demonstrated"}
            return

        try:
            source_trace = await _find_fallback_trace(scenario, recorder_url=recorder_url, exclude_session_id=session_id)
            fallback_id = await replay_trace(source_trace, recorder_url=recorder_url, scenario_id=scenario.scenario_id)
            outcomes[session_id] = {"status": "fallback", "fallback_session_id": str(fallback_id)}
        except Exception:  # noqa: BLE001
            logger.exception("blackbox demo: fallback replay also failed for scenario %s", scenario.scenario_id)
            outcomes[session_id] = {"status": "fallback", "fallback_session_id": None}

    app = FastAPI(title="Blackbox Demo")

    @app.get("/scenarios")
    async def list_scenarios() -> list[dict]:
        return [
            {
                "scenario_id": s.scenario_id, "title": s.title, "mechanism": s.mechanism,
                "is_live": s.is_live, "notes": s.notes,
            }
            for s in SCENARIOS.values()
        ]

    @app.post("/run", response_model=RunResponse)
    async def run_scenario(body: RunRequest, request: Request) -> RunResponse:
        scenario = SCENARIOS.get(body.scenario_id)
        if scenario is None:
            raise HTTPException(status_code=404, detail=f"unknown scenario {body.scenario_id!r}")

        ip = _client_ip(request)
        allowed = True
        reason = ""
        try:
            rate_limiter.check(ip)
        except RateLimitExceeded as exc:
            allowed = False
            reason = str(exc)
        run_log.log_attempt(ip=ip, scenario_id=scenario.scenario_id, allowed=allowed, reason=reason)
        if not allowed:
            raise HTTPException(status_code=429, detail=reason)

        live_attempt_ok = scenario.is_live and KillSwitch.live_runs_enabled()

        if not live_attempt_ok:
            if scenario.recorded_fixture is None:
                raise HTTPException(status_code=503, detail="scenario has no live path and no recorded fallback")
            source_trace = _load_fixture_trace(scenario.recorded_fixture)
            session_id = await replay_trace(source_trace, recorder_url=recorder_url, scenario_id=scenario.scenario_id)
            notice = (
                "showing a recorded run — this scenario is not attempted live"
                if not scenario.is_live else
                "showing a recorded run — live demo runs are temporarily disabled"
            )
            return RunResponse(session_id=str(session_id), mode="recorded", notice=notice)

        # Live path: reset scenario state so the run is reproducible (a
        # ticket already "resolved" by a previous visitor silently defeats
        # the scenario — see the M8 commit for exactly this bug).
        await asyncio.to_thread(seed, northwind_db_path())

        session_token, session_id = await establish_session(
            base_url=mediator_url, client_id=client_id, client_secret=client_secret,
            human_id=scenario.human_id, task_description=scenario.task_description,
            scenario_id=scenario.scenario_id,
        )
        asyncio.create_task(_run_live_agent(session_id, session_token, scenario))
        return RunResponse(session_id=session_id, mode="live")

    @app.get("/run/{session_id}/outcome", response_model=OutcomeResponse)
    async def run_outcome(session_id: str) -> OutcomeResponse:
        outcome = outcomes.get(session_id, {"status": "demonstrated"})  # unknown id: not a live run we started, nothing to wait for
        return OutcomeResponse(**outcome)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "live_runs_enabled": KillSwitch.live_runs_enabled()}

    return app


app = create_app()
