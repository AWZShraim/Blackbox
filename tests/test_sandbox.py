import os

import pytest

from mediator.execution.sandbox import SubprocessSandbox


async def _echo_env(args, *, db_path=None):
    """Test-only handler: reports what the child process can actually see.
    Not registered in the real tool catalogue — this exists purely to prove
    the sandbox scrubs the environment (I3, M4 acceptance)."""
    return {"env_keys": sorted(os.environ.keys()), "db_path_seen": os.environ.get("NORTHWIND_DB_PATH")}


_ECHO_ENV_PATH = f"{_echo_env.__module__}.{_echo_env.__name__}"


@pytest.mark.asyncio
async def test_subprocess_sandbox_scrubs_secrets_from_the_parent_environment(monkeypatch):
    """M4 acceptance: 'agent process holds no credentials (verify by
    inspecting its environment)'. The sandbox is where a tool handler
    actually executes — this proves a secret set in the mediator's own
    process (e.g. ANTHROPIC_API_KEY) never reaches the child that runs a
    tool call."""
    monkeypatch.setenv("BLACKBOX_TEST_SECRET", "sk-super-secret-should-never-leak")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-never-leak-either")

    sandbox = SubprocessSandbox()
    result = await sandbox.execute(
        handler_path=_ECHO_ENV_PATH, arguments={}, env={"NORTHWIND_DB_PATH": "/tmp/does-not-matter.db"}
    )

    assert result.success, result.error
    assert "BLACKBOX_TEST_SECRET" not in result.result["env_keys"]
    assert "ANTHROPIC_API_KEY" not in result.result["env_keys"]


@pytest.mark.asyncio
async def test_subprocess_sandbox_passes_through_only_the_allowlisted_keys():
    sandbox = SubprocessSandbox()
    result = await sandbox.execute(
        handler_path=_ECHO_ENV_PATH,
        arguments={},
        env={"NORTHWIND_DB_PATH": "/tmp/x.db", "AWS_SECRET_ACCESS_KEY": "leak-me-not"},
    )
    assert result.success, result.error
    assert result.result["db_path_seen"] == "/tmp/x.db"
    assert "AWS_SECRET_ACCESS_KEY" not in result.result["env_keys"]


@pytest.mark.asyncio
async def test_subprocess_sandbox_reports_handler_exceptions_without_crashing_the_mediator():
    sandbox = SubprocessSandbox()
    result = await sandbox.execute(
        handler_path="scenarios.tools.definitions.get_ticket",
        arguments={},  # missing required "id" -> KeyError inside the handler
        env={"NORTHWIND_DB_PATH": "/tmp/does-not-exist.db"},
    )
    assert result.success is False
    assert "KeyError" in result.error
