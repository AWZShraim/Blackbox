"""Direct Anthropic API implementation of ModelProvider. Holds the model
API key — this object must only ever be constructed inside the mediator
process, never inside an agent (I3)."""

from __future__ import annotations

from typing import Any

import anthropic

from mediator.providers.base import ModelResponse, ToolCall
from mediator.providers.model_map import resolve_anthropic_model_id


class AnthropicProvider:
    def __init__(self, api_key: str, *, client: anthropic.AsyncAnthropic | None = None) -> None:
        self._client = client or anthropic.AsyncAnthropic(api_key=api_key)

    async def create_message(
        self,
        *,
        model: str,
        system: str | None,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 1024,
    ) -> ModelResponse:
        kwargs: dict[str, Any] = {
            "model": resolve_anthropic_model_id(model),
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        resp = await self._client.messages.create(**kwargs)

        text: str | None = None
        tool_calls: list[ToolCall] = []
        for block in resp.content:
            if block.type == "text":
                text = (text or "") + block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, input=block.input))

        return ModelResponse(
            stop_reason=resp.stop_reason or "end_turn",
            text=text,
            tool_calls=tool_calls,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
        )
