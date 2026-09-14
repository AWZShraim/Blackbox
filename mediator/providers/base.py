"""
Normalized model-provider interface. The mediator's /v1/messages ingress
(Section 6.1) and, before it exists, the M3 direct-transport smoke test both
speak this shape — provider-specific request/response formats (Anthropic
Messages API vs Bedrock Converse API) are translated at the edge, in
anthropic_provider.py / bedrock_provider.py, and never leak past here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class ModelResponse:
    stop_reason: str
    text: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


class ModelProvider(Protocol):
    async def create_message(
        self,
        *,
        model: str,
        system: str | None,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 1024,
    ) -> ModelResponse: ...
