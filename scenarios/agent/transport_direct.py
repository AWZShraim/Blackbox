"""
M3 only: wires the agent loop straight to a ModelProvider and a
ToolRegistry, no mediator in between. The agent process using this holds a
model API key directly — that is only acceptable here, before the mediator
exists. Superseded by transport_mediated.py from M4 onward; loop.py itself
does not change.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mediator.execution.registry import ToolRegistry
from mediator.providers.base import ModelProvider, ModelResponse


class DirectTransport:
    def __init__(
        self,
        *,
        provider: ModelProvider,
        model: str,
        registry: ToolRegistry,
        db_path: Path | None = None,
    ) -> None:
        self._provider = provider
        self._model = model
        self._registry = registry
        self._db_path = db_path

    async def call_model(
        self, *, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ModelResponse:
        return await self._provider.create_message(
            model=self._model, system=system, messages=messages, tools=tools, max_tokens=1024
        )

    async def run_tool(self, name: str, arguments: dict[str, Any], *, tool_call_id: str) -> Any:
        spec = self._registry.get(name)
        if spec is None:
            raise ValueError(f"unknown tool {name!r}")
        return await spec.handler(arguments, db_path=self._db_path)
