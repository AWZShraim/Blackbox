"""
POST /sessions/{id}/contain — the containment control (Section 6.5): stops
forwarding and revokes credentials for a session. Deliberately NOT
authenticated with the agent's own session token — a responder containing
a possibly-compromised agent should never need that agent's own
credentials to do it. Authenticated instead with a separate operator key,
matching how a real deployment would gate this (an SOC responder's own
identity, not the thing being contained).
"""

from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from mediator.core import Mediator, SessionNotFound


class ContainRequest(BaseModel):
    initiated_by: str
    reason: str | None = None


def build_containment_router(mediator: Mediator):
    router = APIRouter()

    def _check_operator_key(x_blackbox_operator_key: str | None) -> None:
        expected = os.environ.get("BLACKBOX_OPERATOR_KEY", "operator-dev-key-change-me")
        if x_blackbox_operator_key != expected:
            raise HTTPException(status_code=401, detail="invalid or missing operator key")

    @router.post("/sessions/{session_id}/contain")
    async def contain(
        session_id: str, body: ContainRequest, x_blackbox_operator_key: str | None = Header(default=None),
    ) -> dict:
        _check_operator_key(x_blackbox_operator_key)
        try:
            await mediator.contain_session(uuid.UUID(session_id), initiated_by=body.initiated_by, reason=body.reason)
        except SessionNotFound as exc:
            raise HTTPException(status_code=404, detail="unknown session") from exc
        return {"contained": True}

    @router.get("/sessions/{session_id}/status")
    async def status(session_id: str) -> dict:
        try:
            session = mediator.get_session(uuid.UUID(session_id))
        except SessionNotFound as exc:
            raise HTTPException(status_code=404, detail="unknown session") from exc
        return {"status": session.status.value}

    return router
