# Blackbox

**EDR for AI agents.** A mediation and forensics layer: every model call,
every tool call, and every tool result an agent makes transits Blackbox,
which records it, verifies it, evaluates it against policy and behavioural
baseline, and enforces decisions.

Blackbox does not primarily exist to prevent incidents. It exists to make
them investigable.

## Status

Built milestone by milestone; see git log. Currently: M1-M7 (the spine
plus detection). M8+ (live incident, containment, demo mode, AWS
deployment, MCP/latency) in progress.

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

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY
python -m scenarios.company.seed
pytest
```

Docker Compose (`deploy/docker-compose.yml`, `make up` / `make seed` /
`make scenario SCENARIO=...`) is written but **unverified on this
machine** — Docker isn't installed here. Verify with a real `docker
compose up` before relying on it.

## Layout

See each top-level package: `common/` (trace schema + interfaces),
`mediator/`, `recorder/`, `detector/`, `investigator/`, `scenarios/`
(the synthetic Northwind Support company, tools, and agent),
`deploy/` (docker-compose + Terraform).
