"""
Tool registry — I4's enforcement point.

I4: `run_bash`, `exec_python`, `eval`, and any equivalent are forbidden from
the tool catalogue. Raw execution is the one thing that breaks the
mediator's visibility guarantee: if the agent can run arbitrary commands,
Blackbox records the command string and is blind to everything it does.
Narrow, semantically meaningful tools keep the record complete.

The registry validates this at load time and refuses to register a tool
marked as raw execution — see `RawExecutionToolError` below. This is
defense in depth on top of Section 6.2 step 2 ("validate the tool is in the
agent's registered catalogue"): a raw-exec tool must never make it into the
catalogue in the first place.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable


class ToolClass(str, Enum):
    read = "read"
    write = "write"


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


ToolHandler = Callable[..., Awaitable[Any]]


class RawExecutionToolError(ValueError):
    """Raised when a tool is rejected because it would grant raw execution."""


# Name patterns that are raw execution by construction, regardless of how a
# tool author labels them. This is defense in depth on top of the explicit
# `raw_exec` flag: a mislabeled tool must not sneak through on a naming
# technicality.
RAW_EXEC_NAME_DENYLIST = frozenset({
    "run_bash", "bash", "sh", "shell", "exec", "exec_python", "eval",
    "run_command", "run_script", "python_exec", "subprocess", "system",
    "run_code", "execute_code", "run_shell_command", "cmd",
})


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    tool_class: ToolClass
    risk: RiskLevel
    handler: ToolHandler
    raw_exec: bool = False
    notes: str = ""


class ToolRegistry:
    """An agent's declared tool catalogue (Section 6.2 step 2 reads from
    this). One registry per agent profile — different agents can be scoped
    to different subsets of the same tool implementations."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.raw_exec or spec.name.lower() in RAW_EXEC_NAME_DENYLIST:
            raise RawExecutionToolError(
                f"refusing to register {spec.name!r}: raw execution tools are "
                "forbidden (I4) — tools must be specific and bounded, e.g. "
                "deploy_service(name, version), not run_bash(cmd)"
            )
        if spec.name in self._tools:
            raise ValueError(f"tool {spec.name!r} is already registered")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def catalogue(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def schemas_for_agent(self) -> list[dict[str, Any]]:
        """Tool schemas in the shape offered to the model — this is what
        populates `model_call.tools_offered` in the trace."""
        return [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in self._tools.values()
        ]
