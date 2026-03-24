from __future__ import annotations

import asyncio

import pytest

from mw4agent.agents.runner.runner import AgentRunner
from mw4agent.agents.session.manager import SessionManager
from mw4agent.agents.tools.base import AgentTool, ToolResult
from mw4agent.agents.tools.registry import ToolRegistry


class _SlowTool(AgentTool):
    def __init__(self) -> None:
        super().__init__(
            name="slow_tool",
            description="slow tool for processing event test",
            parameters={"type": "object"},
            owner_only=False,
        )

    async def execute(self, tool_call_id, params, context=None):
        await asyncio.sleep(0.08)
        return ToolResult(success=True, result={"ok": True})


@pytest.mark.asyncio
async def test_execute_tool_emits_processing_event_for_long_running_tool(tmp_path, monkeypatch) -> None:
    # Shrink timing windows to keep test fast:
    # "超过30s后每60s" => here "超过20ms后每20ms".
    import mw4agent.agents.runner.runner as runner_mod

    monkeypatch.setattr(runner_mod, "TOOL_PROCESSING_START_SEC", 0.02)
    monkeypatch.setattr(runner_mod, "TOOL_PROCESSING_INTERVAL_SEC", 0.02)

    runner = AgentRunner(SessionManager(str(tmp_path / "sessions.json")))
    reg = ToolRegistry()
    reg.register(_SlowTool())
    runner.tool_registry = reg

    result = await runner.execute_tool(
        tool_call_id="tc1",
        tool_name="slow_tool",
        params={},
        context={"run_id": "run1"},
    )
    assert result.success is True

    tool_events = runner.event_stream.get_events(stream="tool")
    types = [e.type for e in tool_events]
    assert "start" in types
    assert "processing" in types
    assert "end" in types
    # Ensure ordering makes sense.
    assert types.index("start") < types.index("processing") < types.index("end")

