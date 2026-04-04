from __future__ import annotations

from pathlib import Path

import pytest

from orbit.agents.tools.exec_tool import ExecTool


@pytest.mark.asyncio
async def test_exec_tool_runs_command_successfully(tmp_path: Path) -> None:
    tool = ExecTool()
    result = await tool.execute(
        "tc1",
        {"command": "echo hello"},
        context={"workspace_dir": str(tmp_path)},
    )
    assert result.success is True
    payload = result.result
    assert payload["exit_code"] == 0
    assert "hello" in payload["stdout"]
    assert payload["timed_out"] is False


@pytest.mark.asyncio
async def test_exec_tool_times_out(tmp_path: Path) -> None:
    tool = ExecTool()
    result = await tool.execute(
        "tc2",
        {"command": "sleep 2", "timeout_ms": 150},
        context={"workspace_dir": str(tmp_path)},
    )
    assert result.success is False
    assert "timed out" in (result.error or "")
    assert result.result["timed_out"] is True


@pytest.mark.asyncio
async def test_exec_tool_workspace_only_blocks_outside_cwd(tmp_path: Path) -> None:
    tool = ExecTool()
    outside = tmp_path.parent
    result = await tool.execute(
        "tc3",
        {"command": "pwd", "cwd": str(outside)},
        context={"workspace_dir": str(tmp_path), "tools_fs_workspace_only": True},
    )
    assert result.success is False
    assert "outside workspace root" in (result.error or "")

