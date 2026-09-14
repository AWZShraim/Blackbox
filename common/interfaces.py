"""
The four seams (build spec Section 4). Three are Python Protocols here; the
fourth — Policy — is declarative YAML evaluated by mediator/policy/engine.py
and deliberately has no Python interface, since the point of that seam is
that policy is data, not code.

Each of Collector, CredentialBroker, and Exporter must ship with at least one
real implementation and be swappable without touching core code. That is
what makes the scaling story (eBPF collector, real STS, a SIEM exporter)
credible instead of aspirational.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from common.schema import Session, Step


@runtime_checkable
class Collector(Protocol):
    """Anything that can emit trace events into Blackbox.

    Ships with the in-mediator collector (mediator/emit.py), which the
    mediator calls into its async queue (I2). Must accept an eBPF collector
    or an MCP-proxy collector later without touching core code — so this
    interface knows nothing about HTTP, queues, or the mediator's internals,
    only about the schema.
    """

    async def emit_session(self, session: Session) -> None:
        """Create or update a session record."""
        ...

    async def emit_step(self, step: Step) -> None:
        """Append one step to a session's trace."""
        ...


@dataclass(frozen=True)
class ScopedCredential:
    """Never returned to the agent (I3). The mediator holds this only for
    the duration of one tool call's execution and discards it; only
    `credential_ref` is ever written to the trace."""

    credential_ref: str
    secret: str
    expires_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class CredentialBroker(Protocol):
    """I3: the agent never receives a database password, API key, or cloud
    token — it receives a session with the mediator, and the mediator mints
    short-lived scoped credentials per tool call.

    Ships with LocalDevBroker (mediator/credentials/local.py, HMAC-signed
    opaque tokens against the scenario's fake backend) and AwsStsBroker
    (mediator/credentials/aws_sts.py, real `sts:AssumeRole` with a session
    policy scoped to the specific tool call).
    """

    async def mint(
        self,
        *,
        session_id: uuid.UUID,
        tool_name: str,
        risk: str,
        ttl_seconds: int,
    ) -> ScopedCredential:
        """Mint a credential scoped to exactly one tool call, with a short
        TTL. Must never be called speculatively — one mint per execution."""
        ...

    async def revoke(self, credential_ref: str) -> None:
        """Revoke one previously minted credential immediately."""
        ...

    async def revoke_session(self, session_id: uuid.UUID) -> None:
        """Revoke every credential outstanding for a session. Called on
        containment (M9) — must complete before the containment_event step
        is emitted, so the trace never claims revocation happened before it
        did."""
        ...


@runtime_checkable
class Exporter(Protocol):
    """Ships with OtlpExporter (gen_ai.* spans, see recorder/otel_mapping.py)
    and StdoutExporter (local dev / CI). Must accept a SIEM exporter later.

    Consumes already-recorded steps/sessions. Never called from the
    mediator's request path (I2) — the recorder drives this after a step has
    landed in Postgres.
    """

    async def export_step(self, session: Session, step: Step) -> None:
        ...

    async def export_session(self, session: Session) -> None:
        ...
