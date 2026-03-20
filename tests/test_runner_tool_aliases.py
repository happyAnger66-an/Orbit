from __future__ import annotations

import pytest

from mw4agent.agents.runner.runner import AgentRunner
from mw4agent.agents.session.manager import SessionManager
from mw4agent.agents.tools.base import AgentTool, ToolResult
from mw4agent.agents.tools.registry import ToolRegistry


class _FakeExecTool(AgentTool):
    def __init__(self) -> None:
        super().__init__(
            name="exec",
            description="fake exec",
            parameters={"type": "object"},
            owner_only=False,
        )

    async def execute(self, tool_call_id, params, context=None):
        return ToolResult(success=True, result={"tool": "exec", "params": params})


@pytest.mark.asyncio
async def test_runner_execute_tool_normalizes_exec_aliases(tmp_path) -> None:
    runner = AgentRunner(SessionManager(str(tmp_path / "sessions.json")))
    custom_registry = ToolRegistry()
    custom_registry.register(_FakeExecTool())
    runner.tool_registry = custom_registry

    for alias in ("bash", "shell_exec", "run_command", "exec", " tools/exec "):
        result = await runner.execute_tool("tc", alias, {"command": "echo hi"}, context={})
        assert result.success is True
        assert result.result["tool"] == "exec"

