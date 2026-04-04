from __future__ import annotations

import pytest

from orbit.agents.tools.process_tool import ProcessTool, _PROCESS_REGISTRY


@pytest.mark.asyncio
async def test_process_tool_start_status_stop(tmp_path) -> None:
    _PROCESS_REGISTRY.clear()
    tool = ProcessTool()
    ctx = {"workspace_dir": str(tmp_path)}

    started = await tool.execute("p1", {"action": "start", "command": "sleep 2"}, context=ctx)
    assert started.success is True
    process_id = started.result["process_id"]
    assert started.result["status"] in ("running", "exited")

    status = await tool.execute("p2", {"action": "status", "process_id": process_id}, context=ctx)
    assert status.success is True
    assert status.result["process_id"] == process_id

    stopped = await tool.execute("p3", {"action": "stop", "process_id": process_id}, context=ctx)
    assert stopped.success is True
    assert stopped.result["status"] == "exited"


@pytest.mark.asyncio
async def test_process_tool_list(tmp_path) -> None:
    _PROCESS_REGISTRY.clear()
    tool = ProcessTool()
    ctx = {"workspace_dir": str(tmp_path)}

    await tool.execute("p1", {"action": "start", "command": "sleep 2"}, context=ctx)
    listed = await tool.execute("p2", {"action": "list"}, context=ctx)
    assert listed.success is True
    assert listed.result["count"] >= 1
    assert isinstance(listed.result["processes"], list)

    # cleanup
    for item in list(listed.result["processes"]):
        await tool.execute("p3", {"action": "stop", "process_id": item["process_id"]}, context=ctx)


@pytest.mark.asyncio
async def test_process_tool_workspace_only_blocks_outside(tmp_path) -> None:
    _PROCESS_REGISTRY.clear()
    tool = ProcessTool()
    outside = tmp_path.parent
    result = await tool.execute(
        "p1",
        {"action": "start", "command": "sleep 1", "cwd": str(outside)},
        context={"workspace_dir": str(tmp_path), "tools_fs_workspace_only": True},
    )
    assert result.success is False
    assert "outside workspace root" in (result.error or "")

