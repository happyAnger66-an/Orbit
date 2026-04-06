"""exec(background/yield_ms) + process registry integration."""

from __future__ import annotations

import asyncio

import pytest

from orbit.agents.tools.exec_tool import ExecTool
from orbit.agents.tools.process_tool import ProcessTool
from orbit.agents.tools.process_session_registry import reset_registry_for_tests


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_registry_for_tests()
    yield
    reset_registry_for_tests()


@pytest.mark.asyncio
async def test_exec_sync_fast_command_no_detach(tmp_path) -> None:
    tool = ExecTool()
    ws = str(tmp_path)
    r = await tool.execute("t1", {"command": "echo hi"}, context={"workspace_dir": ws})
    assert r.success
    assert (r.result or {}).get("stdout", "").strip() == "hi"


@pytest.mark.asyncio
async def test_exec_yield_ms_detaches_then_process_poll(tmp_path) -> None:
    exec_t = ExecTool()
    proc_t = ProcessTool()
    ws = str(tmp_path)
    r = await exec_t.execute(
        "t2",
        {"command": "echo bgout && sleep 3", "yield_ms": 300},
        context={"workspace_dir": ws},
    )
    assert r.success
    body = r.result or {}
    assert body.get("status") == "running"
    sid = body.get("session_id")
    assert isinstance(sid, str) and sid

    await asyncio.sleep(0.15)
    p = await proc_t.execute("p1", {"action": "log", "session_id": sid}, context={"workspace_dir": ws})
    assert p.success
    assert "bgout" in ((p.result or {}).get("text") or "")

    k = await proc_t.execute(
        "k1",
        {"action": "kill", "session_id": sid, "stop_timeout_ms": 2000},
        context={"workspace_dir": ws},
    )
    assert k.success


@pytest.mark.asyncio
async def test_exec_background_immediate_session(tmp_path) -> None:
    exec_t = ExecTool()
    ws = str(tmp_path)
    r = await exec_t.execute(
        "t3",
        {"command": f"sleep 5", "background": True},
        context={"workspace_dir": ws},
    )
    assert r.success
    sid = (r.result or {}).get("session_id")
    assert sid
    proc_t = ProcessTool()
    st = await proc_t.execute("s1", {"action": "status", "session_id": sid}, context={"workspace_dir": ws})
    assert st.success
    assert (st.result or {}).get("status") == "running"
    await proc_t.execute("k2", {"action": "kill", "session_id": sid}, context={"workspace_dir": ws})


@pytest.mark.asyncio
async def test_process_start_list_kill(tmp_path) -> None:
    proc_t = ProcessTool()
    ws = str(tmp_path)
    r = await proc_t.execute(
        "st",
        {"action": "start", "command": "sleep 4"},
        context={"workspace_dir": ws},
    )
    assert r.success
    sid = (r.result or {}).get("session_id")
    lst = await proc_t.execute("ls", {"action": "list"}, context={"workspace_dir": ws})
    assert lst.success
    assert (lst.result or {}).get("count", 0) >= 1
    await proc_t.execute("kx", {"action": "kill", "session_id": sid}, context={"workspace_dir": ws})
