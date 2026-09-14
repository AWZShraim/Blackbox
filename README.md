# Blackbox

**EDR for AI agents.** A mediation and forensics layer: every model call,
every tool call, and every tool result an agent makes transits Blackbox,
which records it, verifies it, evaluates it against policy and behavioural
baseline, and enforces decisions.

Blackbox does not primarily exist to prevent incidents. It exists to make
them investigable.

## Status

Built milestone by milestone; see git log. Currently: M1-M10 (the spine,
detection, a live incident, containment, and the hosted demo). M11 (AWS
deployment) and M12 (MCP endpoint + latency — the MCP endpoint itself is
already built and tested against a real MCP client as part of M4/M8) next.

## Performance

The mediator's policy-plus-baseline evaluation (Section 6.2) — everything
except actual tool execution — measured with `python -m
scripts.measure_latency`:

```
samples=3000
p50=0.0041ms
p99=0.0058ms
under 10ms budget: True
```

(In-process measurement against an `InProcessSandbox` and a populated
baseline, so it isolates the mediator's own overhead from tool-execution
and network cost, per the spec's own carve-out.)

## Local development

Backend:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY
python -m scenarios.company.seed
pytest
```

Run the full stack by hand (four terminals; `make up` does this via Docker
Compose once you have Docker — see below):

```bash
# 1. Postgres — any local Postgres 16, or an ephemeral one for testing:
#    the test suite itself uses `pgserver` (a bundled binary, no install
#    needed) — see tests/conftest.py if you want to reuse that trick.

# 2. Recorder
DATABASE_URL=postgresql+asyncpg://blackbox:blackbox@localhost:5432/blackbox \
  uvicorn recorder.main:app --port 8010

# 3. Mediator
RECORDER_URL=http://localhost:8010 uvicorn mediator.main:app --port 8000

# 4. Demo orchestrator (Section 8)
MEDIATOR_URL=http://localhost:8000 RECORDER_URL=http://localhost:8010 \
  uvicorn scenarios.demo.main:app --port 8020

# 5. Investigator
cd investigator && npm install && npm run dev
```

Then open `http://localhost:3000` — the landing page is the scenario
picker (Section 8): pick a live or recorded scenario, watch it stream in,
toggle between the Responder and Platform Engineer personas, use the
guided tour or switch to free explore.

Docker Compose (`deploy/docker-compose.yml`, `make up` / `make seed` /
`make scenario SCENARIO=...`) is written but **unverified on this
machine** — Docker isn't installed here. Verify with a real `docker
compose up` before relying on it.

## Layout

See each top-level package: `common/` (trace schema + interfaces),
`mediator/`, `recorder/`, `detector/`, `investigator/`, `scenarios/`
(the synthetic Northwind Support company, tools, agent, incident
definitions, and the demo orchestrator under `scenarios/demo/`),
`deploy/` (docker-compose + Terraform).
