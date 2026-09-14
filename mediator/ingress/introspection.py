"""
Read-only introspection for the platform-engineer persona (Section 8):
the declared tool catalogue, the loaded policy, and (if one has been
learned) the baseline. No session token needed — this describes the
agent's static configuration, not anything session-specific.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi import APIRouter

from detector.baseline import BaselineStore
from mediator.execution.registry import ToolRegistry
from mediator.policy.engine import PolicyEngine


def build_introspection_router(
    registry: ToolRegistry, policy: PolicyEngine, *, policy_path: Path, baseline_store: BaselineStore | None = None,
):
    router = APIRouter()

    @router.get("/catalogue")
    async def catalogue() -> list[dict]:
        return [
            {
                "name": t.name, "description": t.description, "tool_class": t.tool_class.value,
                "risk": t.risk.value, "notes": t.notes, "input_schema": t.input_schema,
            }
            for t in registry.catalogue()
        ]

    @router.get("/policy")
    async def policy_doc() -> dict:
        raw = yaml.safe_load(policy_path.read_text())
        return {"policy_id": policy.policy_id, "raw": raw}

    @router.get("/baseline/{subject_type}/{subject_id}")
    async def baseline(subject_type: str, subject_id: str) -> dict | None:
        if baseline_store is None:
            return None
        found = baseline_store.load(subject_type, subject_id)
        return found.model_dump(mode="json") if found else None

    return router
