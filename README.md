# Blackbox

## Why I built this

I kept seeing stories about AI agents going rogue: agents deleting production
databases, taking actions nobody authorised, breaking into systems they had no
business touching. The coverage framed it as models randomly turning on their
operators, and I wanted to understand whether that was actually what was
happening.

It mostly is not. Reading the research, the behaviour is structured and
reproducible rather than random. It comes from a few identifiable places: an
agent facing a conflict between its goal and a constraint, an agent routing
around a stop signal because finishing the task outweighs stopping, an agent
acting on instructions someone planted in a document it retrieved, or an agent
doing exactly what it was told when what it was told was destructive.

What struck me was that in almost every documented case, nobody could explain
afterward why it happened. The decision was made inside a model's reasoning and
the only record was scattered application logs. Organisations were handing
agents real credentials and real permissions with no way to reconstruct their
actions after the fact.

That is the gap I wanted to build for. Not prevention, which is a much harder
and more crowded problem, but investigation. Blackbox is my attempt at the
forensics layer: the thing you wish you had running before the incident, so that
when an agent does something destructive you can actually answer why.

## What it is

Blackbox is a mediation and forensics layer that sits between AI agents and
everything they touch. Agents hold no credentials and have no network egress
except through it. Every model call, tool call, and tool result transits
Blackbox, which records it, evaluates it against policy and a behavioural
baseline, and enforces decisions.

The mental model is EDR for AI agents rather than a firewall. It is not
primarily built to stop incidents. It is built to make them investigable.

## Three design decisions

**Agents hold no credentials.** The mediator mints short-lived scoped
credentials per tool call, backed by AWS STS in the deployed profile. The agent
never receives a database password, API key, or cloud token. Combined with a
private subnet that has no NAT gateway and a security group permitting egress
only to the mediator, bypass is not detected after the fact, it is
architecturally prevented.

**Collection survives containment.** An incident is a chain, not an event. A
contained agent may have already spawned sub-agents, poisoned shared memory, or
queued actions. If the recorder lives inside the agent's process, containment
destroys the evidence at the exact moment it is most needed. The recorder runs
as a separate service, and agent termination is recorded as an event within the
trace, never as the end of it.

**Detection claims are honest.** Blackbox surfaces ranked candidate triggers,
not root cause, and detects departure from declared scope, not intent. Detecting
intent is an open research problem. Detecting scope deviation is tractable and
measurable, so that is what it claims.

## What it detects

Nine detectors across four threat mechanisms:

| Mechanism | Description |
|---|---|
| Reasoning compromise | Instructions injected via retrieved content or tool results |
| Privilege boundary escape | Authorised credentials used in unauthorised ways |
| Corrigibility failure | Agent routes around a stop signal or approval gate |
| Excessive agency | Agent does what it was asked, and what it was asked was destructive |

Plus abuse mode: a human using a legitimate agent as a weapon, detected through
per-user behavioural deviation and attributed to the initiating human rather
than stopping at "the agent did it."

The detectors span policy signals (unknown tool, policy violation), baseline
signals (argument anomaly, sequence anomaly, volume anomaly), provenance
(untrusted influence), content (injection heuristics), and composite patterns
(exfiltration shape, post-stop activity).

## How it works

Every piece of text entering the model's context carries a provenance record:
which tool call introduced it, from what source, at what trust level. System
prompts and registered tool schemas are trusted. Authenticated user input is
semi-trusted. Anything retrieved from a data store is untrusted.

That provenance chain is what makes backward tracing possible. When a detector
flags a tool call, Blackbox walks backward through the trace and scores each
prior step on recency, trust level of the content it introduced, injection
heuristic matches, and textual overlap with the flagged call. The result is a
ranked list of candidate triggers with per-signal explanations.

Baselines are learned per agent and per human, covering tool set, argument
shapes, tool-call sequence bigrams, call volume, and the normal ratio of trusted
to untrusted content. They are versioned and human-editable so an operator can
review a proposed envelope before enabling enforcement. Both services refuse to
start against a baseline too thin to trust, rather than silently suppressing
every flag, because a detector that returns nothing looks identical to a
detector finding nothing wrong.

## Architecture

```mermaid
flowchart TD
    A["<b>Agent</b><br/>no credentials, no egress except to mediator"]

    A -->|"/v1/messages"| ING
    A -->|"/mcp"| ING

    subgraph MED["Mediator (in path)"]
        direction TB
        ING["Ingress<br/><i>session, agent + human identity</i>"]
        POL["Policy engine<br/><i>declarative YAML</i>"]
        CRED["Credential broker<br/><i>short-lived, scoped, per call</i>"]
        EXEC["Sandboxed execution"]
        ING --> POL --> CRED --> EXEC
    end

    EXEC -. "async emit, never blocks a tool call" .-> REC

    REC["<b>Recorder</b><br/>separate process,<br/>survives agent termination"]

    REC --> PG[("Postgres<br/>hot traces")]
    REC --> S3[("S3 + Object Lock<br/>immutable archive")]
    REC --> OTL["OTLP exporter<br/>OpenTelemetry gen_ai"]

    PG --> DET["Detector<br/><i>9 detectors, per-agent<br/>and per-human baselines</i>"]
    DET --> INV["<b>Investigator</b><br/>timeline, context inspector,<br/>containment"]
    PG --> INV

    classDef boundary stroke-width:2px,stroke-dasharray:4 3
    class MED boundary
```

The MCP endpoint matters for adoption. Any MCP-speaking client can be
instrumented by changing one line of configuration, with no code changes to the
agent, which means Blackbox can record agents it was not built alongside.

Four pluggable interfaces: `Collector`, `CredentialBroker`, `Exporter`, and
declarative YAML policy. Each ships with more than one implementation, so an
eBPF collector or a SIEM exporter plugs in without touching core code.

## Investigator

A Next.js interface built around the responder workflow. Session timeline
colour-coded by step type and risk. A step inspector showing full payloads,
timing, policy decisions, and which credential was minted. A context inspector
that renders the full context window at any step, with each segment tagged by
source and trust level and suspected injections highlighted inline.

From a flagged step, backward tracing navigates to ranked candidate triggers and
opens the context inspector positioned at the relevant content. Containment
controls stop forwarding and revoke credentials, after which the timeline
continues updating with the agent's refused attempts.

## Performance

Mediator policy and baseline evaluation, excluding tool execution and network:

```
p50 = 4.1us
p99 = 5.8us
n   = 3000
```

Measured in-process with `python -m scripts.measure_latency` against a populated
baseline. This isolates the mediator's own overhead and does not include tool
execution or network round trips.

## Test environment

A synthetic support company with seeded data and a ten-tool catalogue spanning
read, write, and critical risk classes. Raw execution tools such as `run_bash`
are rejected at registration, because arbitrary shell access would let an agent
act through a tool rather than as a tool and break the visibility guarantee the
whole design depends on.

Five incident scenarios cover the four threat mechanisms plus abuse mode. Three
run live against a real model. Two ship as recorded traces, because goal
conflict and corrigibility failure need elaborate setups and do not reliably
reproduce, and an unreliable scenario is worse than an honestly labelled
recording.

Detection is developed and tested against hand-written fixture traces rather
than only live runs, so it is deterministic in CI. 100 tests currently pass.

## Local development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY
python -m scenarios.company.seed
python -m scenarios.demo.seed_baseline
pytest
```

Running the stack by hand, five terminals:

```bash
# 1. Postgres 16, local or ephemeral.
#    The test suite uses pgserver (bundled binary, no install). See tests/conftest.py.

# 2. Recorder
DATABASE_URL=postgresql+asyncpg://blackbox:blackbox@localhost:5432/blackbox \
  BLACKBOX_BASELINE_DIR=scenarios/demo/.baselines \
  uvicorn recorder.main:app --port 8010

# 3. Mediator
RECORDER_URL=http://localhost:8010 \
  BLACKBOX_BASELINE_DIR=scenarios/demo/.baselines \
  uvicorn mediator.main:app --port 8000

# 4. Scenario orchestrator
MEDIATOR_URL=http://localhost:8000 RECORDER_URL=http://localhost:8010 \
  uvicorn scenarios.demo.main:app --port 8020

# 5. Investigator
cd investigator && npm install && npm run dev
```

Then open `http://localhost:3000`.

Docker Compose (`deploy/docker-compose.yml`, with `make up`, `make seed`, and
`make scenario SCENARIO=...`) is written but not yet verified end to end.

## Deployment

`deploy/terraform/` has two AWS profiles, with cost breakdowns at the top of
each tfvars file.

- `envs/demo.tfvars`: single AZ, RDS rather than Aurora, no PrivateLink, Fargate
  Spot, GOVERNANCE-mode Object Lock so teardown can empty the archive bucket.
  Built for a short deploy, verify, and destroy cycle.
- `envs/reference.tfvars`: the full enterprise topology. Multi-AZ, Aurora
  Serverless v2, PrivateLink, COMPLIANCE-mode Object Lock, Cognito. It documents
  the production architecture rather than running it.

```bash
make tf-fmt
make tf-validate
make tf-plan-demo            # requires AWS credentials
make destroy PROFILE=demo
```

Agent tasks run in a private subnet with no NAT gateway, and their security
group permits egress only to the mediator. Model access goes through Bedrock
over a VPC interface endpoint, so no component in the stack reaches the public
internet.

`deploy/selfhost/` runs the same services behind Caddy for automatic HTTPS on a
small VPS.

## Repository layout

| Path | Contents |
|---|---|
| `common/` | Trace schema and the four interface protocols |
| `mediator/` | Ingress, policy engine, credential brokers, sandboxed execution |
| `recorder/` | Separate recording service, storage, OpenTelemetry mapping |
| `detector/` | Baseline learning, nine detectors, candidate trigger ranking |
| `investigator/` | Next.js investigation UI |
| `scenarios/` | Synthetic company, tools, agent loop, incident definitions |
| `deploy/` | Docker Compose, Terraform, self-host profile |

## Notes on the OpenTelemetry mapping

Blackbox emits OpenTelemetry GenAI semantic conventions rather than a
proprietary format, so traces land in whatever the operator already runs. Those
conventions are still marked Development status and no `gen_ai.*` attribute has
reached Stable, so the schema version is pinned in a constant and the entire
mapping lives in `recorder/otel_mapping.py`. A spec change is a single file edit.

Prompt text, tool arguments, and results are emitted as span events rather than
span attributes. Attributes are always indexed and size limited, and would
expose PII in whatever backend receives them. Events can be dropped or filtered
at the collector without touching application code.

## Known gaps

- Runtime execution escape detection is out of scope. It needs eBPF, and is
  mitigated architecturally through credential brokering and network policy
  rather than detected. Instrumenting the execution sandbox is the documented
  next step.
- Detection identifies scope deviation, not intent.
- Endpoint agents outside the cloud boundary are not covered.
- Single tenant. The control plane and data plane split is documented but not
  built.
- Docker Compose is written but not verified end to end.
- Terraform validates and plans cleanly but has not yet been applied.

## License

MIT
