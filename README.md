# Blackbox

**EDR for AI agents.** A mediation and forensics layer: every model call,
every tool call, and every tool result an agent makes transits Blackbox,
which records it, verifies it, evaluates it against policy and behavioural
baseline, and enforces decisions.

Blackbox does not primarily exist to prevent incidents. It exists to make
them investigable.

## Status

Built milestone by milestone; see git log. Currently: M1-M3.

## Local development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY
python -m scenarios.company.seed
pytest
```

## Layout

See each top-level package: `common/` (trace schema + interfaces),
`mediator/`, `recorder/`, `detector/`, `investigator/`, `scenarios/`
(the synthetic Northwind Support company, tools, and agent),
`deploy/` (docker-compose + Terraform).
