"""
POST /v1/messages — Anthropic Messages API compatible LLM proxy (Section
6.1). The agent points ANTHROPIC_BASE_URL here; the mediator forwards
upstream and records both directions (I6).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from mediator.core import Mediator, SessionNotFound, TokenBudgetExceeded, ToolNotAllowed
from mediator.ingress.session import SessionAuthError, SessionStore


class MessagesRequest(BaseModel):
    model: str
    system: str | None = None
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]] = []
    max_tokens: int = 1024


def to_anthropic_shape(response) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    if response.text:
        content.append({"type": "text", "text": response.text})
    for call in response.tool_calls:
        content.append({"type": "tool_use", "id": call.id, "name": call.name, "input": call.input})
    return {
        "type": "message",
        "role": "assistant",
        "content": content,
        "stop_reason": response.stop_reason,
        "usage": {"input_tokens": response.input_tokens, "output_tokens": response.output_tokens},
    }


def build_messages_router(mediator: Mediator, sessions: SessionStore):
    router = APIRouter()

    @router.post("/v1/messages")
    async def messages(body: MessagesRequest, request: Request) -> dict[str, Any]:
        auth = request.headers.get("authorization", "")
        token = auth.removeprefix("Bearer ").strip() if auth else None
        try:
            session_id = sessions.resolve(token)
        except SessionAuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

        try:
            response = await mediator.handle_model_call(
                session_id=session_id,
                model=body.model,
                system_prompt=body.system,
                messages=body.messages,
                tools_offered=body.tools,
                max_tokens=body.max_tokens,
            )
        except SessionNotFound as exc:
            raise HTTPException(status_code=404, detail="unknown session") from exc
        except ToolNotAllowed as exc:
            # 423 Locked: forwarding stopped by containment, not a normal 4xx.
            raise HTTPException(status_code=423, detail=str(exc)) from exc
        except TokenBudgetExceeded as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc

        return to_anthropic_shape(response)

    return router
