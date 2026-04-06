from __future__ import annotations

import pytest

from orbit.agents.tools.process_tool import ProcessTool
from orbit.agents.tools.process_session_registry import reset_registry_for_tests


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_registry_for_tests()
    yield
    reset_registry_for_tests()


@pytest.mark.asyncio
async def test_process_tool_start_status_stop(tmp_path) -> None:
    tool = ProcessTool()
    ctx = {"workspace_dir": str(tmp_path)}

    started = await tool.execute("p1", {"action": "start", "command": "sleep 2"}, context=ctx)
    assert started.success is True
    session_id = started.result["session_id"]
    assert started.result["status"] == "running"

    status = await tool.execute("p2", {"action": "status", "session_id": session_id}, context=ctx)
    assert status.success is True
    assert status.result["session_id"] == session_id

    stopped = await tool.execute("p3", {"action": "stop", "session_id": session_id}, context=ctx)
    assert stopped.success is True


@pytest.mark.asyncio
async def test_process_tool_list(tmp_path) -> None:
    tool = ProcessTool()
    ctx = {"workspace_dir": str(tmp_path)}

    await tool.execute("p1", {"action": "start", "command": "sleep 2"}, context=ctx)
    listed = await tool.execute("p2", {"action": "list"}, context=ctx)
    assert listed.success is True
    assert listed.result["count"] >= 1
    assert isinstance(listed.result["sessions"], list)

    for item in list(listed.result["sessions"]):
        sid = item.get("session_id")
        if item.get("status") == "running" and sid:
            await tool.execute("p3", {"action": "stop", "session_id": sid}, context=ctx)


@pytest.mark.asyncio
async def test_process_tool_workspace_only_blocks_outside(tmp_path) -> None:
    tool = ProcessTool()
    outside = tmp_path.parent
    result = await tool.execute(
        "p1",
        {"action": "start", "command": "sleep 1", "cwd": str(outside)},
        context={"workspace_dir": str(tmp_path), "tools_fs_workspace_only": True},
    )
    assert result.success is False
    assert "outside workspace root" in (result.error or "")
