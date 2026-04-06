"""Integration tests for ``orbit.gateway.subagents_cmd`` (requires FastAPI)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

pytest.importorskip("fastapi", reason="gateway stack (FastAPI) not installed")

from orbit.gateway.state import GatewayState
from orbit.gateway.subagents_cmd import execute_subagents_command, schedule_subagents_if_needed
from orbit.gateway.subagents_logic import DesktopSubagentRecord


def test_execute_subagents_empty_shows_help() -> None:
    async def _run() -> None:
        st = GatewayState()
        runner = MagicMock()
        await execute_subagents_command(
            state=st,
            runner=runner,
            agent_manager=MagicMock(),
            session_manager=MagicMock(),
            message="/subagents",
            parent_agent_id="main",
            parent_session_id="sid-1",
            parent_session_key="desktop-app",
            cli_run_id="cli-run-1",
            reasoning_level=None,
        )
        rec = st.runs["cli-run-1"]
        assert rec.snapshot is not None
        assert rec.snapshot.status == "ok"
        assert rec.snapshot.reply_text
        assert "list" in (rec.snapshot.reply_text or "")
        runner.run.assert_not_called()

    asyncio.run(_run())


def test_execute_subagents_list_empty() -> None:
    async def _run() -> None:
        st = GatewayState()
        await execute_subagents_command(
            state=st,
            runner=MagicMock(),
            agent_manager=MagicMock(),
            session_manager=MagicMock(),
            message="/subagents list",
            parent_agent_id="main",
            parent_session_id="sid-1",
            parent_session_key="desktop-app",
            cli_run_id="cli-2",
            reasoning_level=None,
        )
        assert "暂无" in (st.runs["cli-2"].snapshot.reply_text or "")

    asyncio.run(_run())


def test_schedule_subagents_if_needed_branching() -> None:
    async def _run() -> None:
        st = GatewayState()
        tasks: list[asyncio.Task] = []

        def _ct(coro):  # type: ignore[no-untyped-def]
            t = asyncio.create_task(coro)
            tasks.append(t)
            return t

        assert (
            schedule_subagents_if_needed(
                state=st,
                runner=MagicMock(),
                agent_manager=MagicMock(),
                session_manager=MagicMock(),
                message_after_reset="hello",
                parent_agent_id="main",
                parent_session_id="x",
                parent_session_key="desktop-app",
                cli_run_id="r1",
                reasoning_level=None,
                create_task=_ct,
            )
            is False
        )
        assert tasks == []

        ok = schedule_subagents_if_needed(
            state=st,
            runner=MagicMock(),
            agent_manager=MagicMock(),
            session_manager=MagicMock(),
            message_after_reset="/subagents list",
            parent_agent_id="main",
            parent_session_id="sid-1",
            parent_session_key="desktop-app",
            cli_run_id="r2",
            reasoning_level=None,
            create_task=_ct,
        )
        assert ok is True
        assert len(tasks) == 1
        await tasks[0]

    asyncio.run(_run())


def test_kill_marks_cancelled_when_task_not_done() -> None:
    async def _run() -> None:
        st = GatewayState()
        r = DesktopSubagentRecord(
            run_id="child-run-uuid-1111",
            parent_agent_id="main",
            parent_session_id="sid-k",
            parent_session_key="desktop-app",
            child_session_id="c-k",
            child_session_key="desktop-app:subagent:c-k",
            target_agent_id="main",
            task="x",
        )

        async def _slow() -> None:
            await asyncio.sleep(3600)

        r.asyncio_task = asyncio.create_task(_slow())
        st.desktop_subagents.append(r)

        await execute_subagents_command(
            state=st,
            runner=MagicMock(),
            agent_manager=MagicMock(),
            session_manager=MagicMock(),
            message="/subagents kill #1",
            parent_agent_id="main",
            parent_session_id="sid-k",
            parent_session_key="desktop-app",
            cli_run_id="cli-k",
            reasoning_level=None,
        )
        assert r.status == "cancelled"
        r.asyncio_task.cancel()
        try:
            await r.asyncio_task
        except asyncio.CancelledError:
            pass

    asyncio.run(_run())
