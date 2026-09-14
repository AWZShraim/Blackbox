"""
Per-call sandboxed execution (Section 6.2 step 6). For the PoC this is one
OS subprocess per tool call, with a scrubbed environment — I3's other half:
even a handler that tried to read an ambient credential would find none,
only whatever the mediator explicitly passed in `env` for this one call.

`Sandbox` is a Protocol so a container-per-call implementation can replace
this later without any caller (mediator/core.py) changing.
"""

from __future__ import annotations

import asyncio
import multiprocessing as mp
import os
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

# Only these keys survive into the child's environment, regardless of what
# the parent process has set. Model/cloud API keys are never in this list —
# a tool handler has no legitimate reason to see one (I3).
ALLOWED_CHILD_ENV_KEYS = frozenset({"PATH", "PYTHONPATH", "NORTHWIND_DB_PATH"})


@dataclass
class SandboxResult:
    sandbox_id: str
    success: bool
    result: Any
    error: str | None


class Sandbox(Protocol):
    async def execute(
        self,
        *,
        handler_path: str,
        arguments: dict[str, Any],
        env: dict[str, str],
        timeout_s: float = 10.0,
    ) -> SandboxResult: ...


def _child_entry(handler_path: str, arguments: dict[str, Any], env: dict[str, str], conn) -> None:
    import importlib

    os.environ.clear()
    os.environ.update({k: v for k, v in env.items() if k in ALLOWED_CHILD_ENV_KEYS})

    try:
        module_path, func_name = handler_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        handler = getattr(module, func_name)
        db_path = env.get("NORTHWIND_DB_PATH")
        result = asyncio.run(handler(arguments, db_path=db_path))
        conn.send(("ok", result))
    except Exception as exc:  # noqa: BLE001 - reported to the mediator, not raised in-process
        conn.send(("error", f"{exc.__class__.__name__}: {exc}"))
    finally:
        conn.close()


class SubprocessSandbox:
    """One subprocess per tool call. Never holds a scoped credential itself
    — the mediator mints one (Section 6.2 step 5), passes only the minimum
    the sandbox needs through `env`, and revokes it once the call returns
    (step 7). Uses the 'spawn' start method so the child never inherits a
    copy-on-write view of the parent's memory (fork would leak everything
    the scrubbed env is trying to hide)."""

    def __init__(self) -> None:
        self._ctx = mp.get_context("spawn")

    async def execute(
        self,
        *,
        handler_path: str,
        arguments: dict[str, Any],
        env: dict[str, str],
        timeout_s: float = 10.0,
    ) -> SandboxResult:
        sandbox_id = f"sandbox:{uuid.uuid4()}"
        parent_conn, child_conn = self._ctx.Pipe()
        proc = self._ctx.Process(
            target=_child_entry, args=(handler_path, arguments, env, child_conn)
        )
        proc.start()
        child_conn.close()  # only the child should hold the writable end

        loop = asyncio.get_running_loop()
        try:
            status, payload = await asyncio.wait_for(
                loop.run_in_executor(None, parent_conn.recv), timeout=timeout_s
            )
        except asyncio.TimeoutError:
            proc.terminate()
            return SandboxResult(sandbox_id=sandbox_id, success=False, result=None, error="timeout")
        except EOFError:
            return SandboxResult(
                sandbox_id=sandbox_id, success=False, result=None,
                error="sandbox process exited without a result",
            )
        finally:
            proc.join(timeout=1)
            if proc.is_alive():
                proc.kill()
            parent_conn.close()

        if status == "ok":
            return SandboxResult(sandbox_id=sandbox_id, success=True, result=payload, error=None)
        return SandboxResult(sandbox_id=sandbox_id, success=False, result=None, error=payload)


class InProcessSandbox:
    """Test/dev-only stand-in that skips process isolation entirely, for
    fast unit tests of mediator logic that isn't testing the sandbox itself.
    Never used by mediator/main.py at runtime."""

    async def execute(
        self,
        *,
        handler_path: str,
        arguments: dict[str, Any],
        env: dict[str, str],
        timeout_s: float = 10.0,
    ) -> SandboxResult:
        import importlib

        sandbox_id = f"sandbox:{uuid.uuid4()}"
        try:
            module_path, func_name = handler_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            handler = getattr(module, func_name)
            db_path = env.get("NORTHWIND_DB_PATH")
            result = await handler(arguments, db_path=db_path)
            return SandboxResult(sandbox_id=sandbox_id, success=True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return SandboxResult(
                sandbox_id=sandbox_id, success=False, result=None,
                error=f"{exc.__class__.__name__}: {exc}",
            )
