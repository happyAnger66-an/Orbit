from __future__ import annotations

from mw4agent.agents.types import StreamEvent
from mw4agent.agents.session.manager import SessionManager
from mw4agent.channels.feishu_agent_progress import (
    FEISHU_TOOL_PROGRESS_META_KEY,
    feishu_session_wants_tool_progress,
    format_agent_stream_event_for_feishu,
    parse_feishu_tool_progress_command,
)


def test_format_tool_start_and_end() -> None:
    start = StreamEvent(
        stream="tool",
        type="start",
        data={
            "run_id": "r1",
            "tool_name": "read",
            "params": {"path": "a.txt"},
        },
    )
    t1 = format_agent_stream_event_for_feishu(start)
    assert t1 is not None
    assert "read" in t1
    assert "a.txt" in t1 or "path" in t1

    end_ok = StreamEvent(
        stream="tool",
        type="end",
        data={
            "run_id": "r1",
            "tool_name": "read",
            "success": True,
            "result": {"ok": True},
        },
    )
    t2 = format_agent_stream_event_for_feishu(end_ok)
    assert t2 is not None
    assert "read" in t2
    assert "ok" in t2

    end_fail = StreamEvent(
        stream="tool",
        type="end",
        data={
            "run_id": "r1",
            "tool_name": "read",
            "success": False,
            "result": {"error": "denied"},
        },
    )
    t3 = format_agent_stream_event_for_feishu(end_fail)
    assert t3 is not None
    assert "未成功" in t3 or "denied" in t3


def test_format_tool_error() -> None:
    ev = StreamEvent(
        stream="tool",
        type="error",
        data={
            "run_id": "r1",
            "tool_name": "exec",
            "error": "boom",
        },
    )
    t = format_agent_stream_event_for_feishu(ev)
    assert t is not None
    assert "boom" in t


def test_parse_tool_progress_commands() -> None:
    assert parse_feishu_tool_progress_command("/tool_exec_start") == (True, "")
    assert parse_feishu_tool_progress_command("  /tool_exec_start  ") == (True, "")
    assert parse_feishu_tool_progress_command("/tool_exec_start do something") == (True, "do something")
    assert parse_feishu_tool_progress_command("/tool_exec_start\ndo something") == (True, "do something")
    assert parse_feishu_tool_progress_command("/tool_exec_stop") == (False, "")
    assert parse_feishu_tool_progress_command("/tool_exec_stop x") == (False, "x")
    cmd, rest = parse_feishu_tool_progress_command("hello")
    assert cmd is None and rest == "hello"


def test_feishu_session_wants_tool_progress(tmp_path) -> None:
    sm = SessionManager(str(tmp_path / "s.json"))
    assert feishu_session_wants_tool_progress(sm, "sid") is False
    e = sm.get_or_create_session("sid", "key:1", "main")
    meta = dict(e.metadata or {})
    meta[FEISHU_TOOL_PROGRESS_META_KEY] = True
    sm.update_session("sid", metadata=meta)
    assert feishu_session_wants_tool_progress(sm, "sid") is True


def test_format_skips_non_tool_stream() -> None:
    ev = StreamEvent(
        stream="assistant",
        type="delta",
        data={"run_id": "r1", "text": "hi"},
    )
    assert format_agent_stream_event_for_feishu(ev) is None
