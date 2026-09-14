"""
Session establishment (Section 6.1). The agent authenticates with a client
ID and secret, receives a session token bound to agent_id + human_id +
task_description (I7). All subsequent calls carry the token. A call
without a valid session is rejected and logged.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from common.schema import HumanContext
from mediator.core import Mediator, SessionNotFound


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


class SessionAuthError(Exception):
    pass


@dataclass
class ClientCredential:
    client_id: str
    client_secret_hash: str
    agent_id: str
    agent_version: str


class SessionStore:
    """Maps opaque bearer tokens to Blackbox session_ids, and holds the
    registered client credentials an agent authenticates with. In-memory
    for the PoC; a real deployment backs this with the same durable store
    as everything else, not a Python dict."""

    def __init__(self) -> None:
        self._clients: dict[str, ClientCredential] = {}
        self._tokens: dict[str, uuid.UUID] = {}

    def register_client(self, *, client_id: str, client_secret: str, agent_id: str, agent_version: str) -> None:
        self._clients[client_id] = ClientCredential(
            client_id=client_id, client_secret_hash=hash_secret(client_secret),
            agent_id=agent_id, agent_version=agent_version,
        )

    def authenticate(self, *, client_id: str, client_secret: str) -> ClientCredential:
        cred = self._clients.get(client_id)
        if cred is None or not hmac.compare_digest(cred.client_secret_hash, hash_secret(client_secret)):
            raise SessionAuthError("invalid client credentials")
        return cred

    def issue_token(self, session_id: uuid.UUID) -> str:
        token = secrets.token_urlsafe(32)
        self._tokens[token] = session_id
        return token

    def resolve(self, token: str | None) -> uuid.UUID:
        if token is None or token not in self._tokens:
            raise SessionAuthError("missing or invalid session token")
        return self._tokens[token]

    def revoke_token_for_session(self, session_id: uuid.UUID) -> None:
        for tok in [t for t, sid in self._tokens.items() if sid == session_id]:
            del self._tokens[tok]


class EstablishRequest(BaseModel):
    client_id: str
    client_secret: str
    human_id: str
    task_description: str
    human_role: str | None = None
    human_team: str | None = None
    human_auth_method: str | None = None
    scenario_id: str | None = None


class EstablishResponse(BaseModel):
    session_token: str
    session_id: str


class LifecycleRequest(BaseModel):
    event: str
    reason: str | None = None
    initiated_by: str | None = None


def build_session_router(mediator: Mediator, sessions: SessionStore):
    router = APIRouter()

    @router.post("/session/establish", response_model=EstablishResponse)
    async def establish(body: EstablishRequest) -> EstablishResponse:
        try:
            cred = sessions.authenticate(client_id=body.client_id, client_secret=body.client_secret)
        except SessionAuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

        session = await mediator.create_session(
            agent_id=cred.agent_id,
            agent_version=cred.agent_version,
            human_id=body.human_id,
            task_description=body.task_description,
            scenario_id=body.scenario_id,
            human_context=HumanContext(
                role=body.human_role, team=body.human_team, auth_method=body.human_auth_method
            ),
        )
        token = sessions.issue_token(session.session_id)
        return EstablishResponse(session_token=token, session_id=str(session.session_id))

    @router.post("/session/{session_id}/lifecycle")
    async def lifecycle(session_id: str, body: LifecycleRequest, request: Request) -> dict:
        """I1: deliberately reachable independently of the agent — a
        supervisor that detects an agent process died can call this with
        event="terminated" using the same session token even though the
        agent itself no longer exists to call anything."""
        auth = request.headers.get("authorization", "")
        token = auth.removeprefix("Bearer ").strip() if auth else None
        try:
            resolved_id = sessions.resolve(token)
        except SessionAuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        if str(resolved_id) != session_id:
            raise HTTPException(status_code=403, detail="session token does not match session_id in path")

        try:
            step = await mediator.record_lifecycle_event(
                resolved_id, event=body.event, reason=body.reason, initiated_by=body.initiated_by,
            )
        except SessionNotFound as exc:
            raise HTTPException(status_code=404, detail="unknown session") from exc
        return {"step_id": str(step.step_id)}

    return router
