"""Desktop chat `/subagents` slash commands (OpenClaw-inspired, Orbit-local).

Scoped to the current main session (agentId + parent sessionId + sessionKey).
Child runs use a dedicated session_key so they can execute in parallel with the main queue lane.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Callable, Optional

from ..agents.types import AgentRunParams, AgentRunStatus
from ..log import get_logger
from ..memory.bootstrap import load_bootstrap_system_prompt
from .state import GatewayState, RunSnapshot
from .subagents_logic import (
    DesktopSubagentRecord,
    filter_subagents_for_parent,
    read_text_file_tail,
    resolve_subagent_list_spec,
    resolve_transcript_path_for_manager,
    subagents_help_markdown,
)
from .subagents_parse import (
    is_subagents_command_line,
    parse_spawn_agent_and_task,
    split_subagents_args,
)
from .types import AgentEvent

logger = get_logger(__name__)


def _now_ms() -> int:
    return int(time.time() * 1000)


async def _emit_cli_reply(
    *,
    state: GatewayState,
    run_id: str,
    session_key: str,
    session_id: str,
    agent_id: str,
    reply_text: str,
) -> None:
    rec = state.ensure_run(run_id=run_id, session_key=session_key, agent_id=agent_id)
    rec.seq += 1
    await state.broadcast(
        AgentEvent(
            run_id=run_id,
            stream="lifecycle",
            data={
                "phase": "start",
                "startedAt": _now_ms(),
                "session_id": session_id,
                "session_key": session_key,
                "agent_id": agent_id,
            },
            seq=rec.seq,
        )
    )
    rec.reply_text_buffer = reply_text
    rec.seq += 1
    await state.broadcast(
        AgentEvent(
            run_id=run_id,
            stream="assistant",
            data={"type": "delta", "text": reply_text, "final": True},
            seq=rec.seq,
        )
    )
    ended = _now_ms()
    rec.seq += 1
    await state.broadcast(
        AgentEvent(
            run_id=run_id,
            stream="lifecycle",
            data={"phase": "end", "endedAt": ended},
            seq=rec.seq,
        )
    )
    state.mark_run_terminal(
        run_id,
        RunSnapshot(
            run_id=run_id,
            status="ok",
            started_at=rec.started_at_ms,
            ended_at=ended,
            reply_text=reply_text.strip(),
            stop_reason="subagents_cli",
        ),
    )


async def execute_subagents_command(
    *,
    state: GatewayState,
    runner: AgentRunner,
    agent_manager: AgentManager,
    session_manager: SessionManager,
    message: str,
    parent_agent_id: str,
    parent_session_id: str,
    parent_session_key: str,
    cli_run_id: str,
    reasoning_level: Optional[str],
) -> None:
    """Run inside asyncio.create_task; emits WS + run snapshot for ``cli_run_id``."""
    raw = (message or "").strip()
    lowered = raw.lower()
    if not lowered.startswith("/subagents"):
        return

    rest = raw[len("/subagents") :].strip()
    try:
        parts = split_subagents_args(rest)
    except ValueError as e:
        await _emit_cli_reply(
            state=state,
            run_id=cli_run_id,
            session_key=parent_session_key,
            session_id=parent_session_id,
            agent_id=parent_agent_id,
            reply_text=str(e),
        )
        return

    verb = (parts[0] or "").lower() if parts else ""
    args = parts[1:] if len(parts) > 1 else []

    try:
        if not verb or verb in ("help", "-h", "--help"):
            text = subagents_help_markdown()
        elif verb == "list":
            rows = filter_subagents_for_parent(
                state.desktop_subagents, parent_agent_id, parent_session_id
            )
            if not rows:
                text = "（暂无子运行）当前主会话下还没有通过 `/subagents spawn` 启动的任务。"
            else:
                lines = []
                for i, r in enumerate(rows, start=1):
                    lines.append(
                        f"{i}. **{r.status}** · runId `{r.run_id[:8]}…` · agent `{r.target_agent_id}` · "
                        f"childSession `{r.child_session_id[:8]}…`\n"
                        f"   task: {r.task[:200]}{'…' if len(r.task) > 200 else ''}"
                    )
                text = "\n".join(lines)
        elif verb == "info":
            if not args:
                raise ValueError("用法: `/subagents info <#序号|runId前缀>`")
            recs = filter_subagents_for_parent(
                state.desktop_subagents, parent_agent_id, parent_session_id
            )
            r = resolve_subagent_list_spec(recs, args[0])
            if not r:
                raise ValueError("未找到匹配记录（用 `/subagents list` 查看序号）")
            tpath = resolve_transcript_path_for_manager(
                session_manager, r.child_session_id, r.target_agent_id
            )
            text = (
                f"**runId** `{r.run_id}`\n"
                f"**status** {r.status}\n"
                f"**targetAgent** `{r.target_agent_id}`\n"
                f"**childSessionId** `{r.child_session_id}`\n"
                f"**childSessionKey** `{r.child_session_key}`\n"
                f"**task** {r.task}\n"
                f"**transcript** `{tpath}`"
            )
        elif verb == "log":
            if not args:
                raise ValueError("用法: `/subagents log <#|runId前缀> [行数]`")
            recs = filter_subagents_for_parent(
                state.desktop_subagents, parent_agent_id, parent_session_id
            )
            r = resolve_subagent_list_spec(recs, args[0])
            if not r:
                raise ValueError("未找到匹配记录")
            n_lines = 40
            if len(args) >= 2:
                try:
                    n_lines = int(args[1])
                except ValueError:
                    raise ValueError("行数必须是整数")
            path = resolve_transcript_path_for_manager(
                session_manager, r.child_session_id, r.target_agent_id
            )
            tail = read_text_file_tail(path, n_lines)
            text = f"**transcript** `{path}`（末 {n_lines} 行）\n\n```\n{tail}\n```"
        elif verb == "kill":
            if not args:
                raise ValueError("用法: `/subagents kill <#|runId前缀|all>`")
            spec = args[0].strip()
            recs = filter_subagents_for_parent(
                state.desktop_subagents, parent_agent_id, parent_session_id
            )
            if spec.lower() == "all":
                n = 0
                for r in recs:
                    if r.status == "running" and r.asyncio_task and not r.asyncio_task.done():
                        r.asyncio_task.cancel()
                        r.status = "cancelled"
                        n += 1
                text = f"已对 {n} 个运行中的子任务发送取消（尽力而为）。"
            else:
                r = resolve_subagent_list_spec(recs, spec)
                if not r:
                    raise ValueError("未找到匹配记录")
                if r.status == "running" and r.asyncio_task and not r.asyncio_task.done():
                    r.asyncio_task.cancel()
                    r.status = "cancelled"
                    text = f"已对 run `{r.run_id}` 发送取消。"
                else:
                    text = f"记录 `{r.run_id}` 当前状态为 {r.status}，无需取消。"
        elif verb == "spawn":
            aid, task = parse_spawn_agent_and_task(args)
            child_sid = str(uuid.uuid4())
            child_sk = f"{parent_session_key}:subagent:{child_sid}"
            child_run_id = str(uuid.uuid4())

            workspace_dir = agent_manager.get_or_create(aid).workspace_dir
            bootstrap = load_bootstrap_system_prompt(workspace_dir)
            extra = bootstrap.strip() if bootstrap else None

            rec = DesktopSubagentRecord(
                run_id=child_run_id,
                parent_agent_id=parent_agent_id,
                parent_session_id=parent_session_id,
                parent_session_key=parent_session_key,
                child_session_id=child_sid,
                child_session_key=child_sk,
                target_agent_id=aid,
                task=task,
            )
            state.desktop_subagents.append(rec)

            async def _bg() -> None:
                try:
                    result = await runner.run(
                        AgentRunParams(
                            message=task,
                            run_id=child_run_id,
                            session_key=child_sk,
                            session_id=child_sid,
                            agent_id=aid,
                            channel="desktop",
                            deliver=False,
                            extra_system_prompt=extra,
                            workspace_dir=workspace_dir,
                            reasoning_level=(reasoning_level or "").strip() or None,
                        )
                    )
                    st = getattr(result.meta, "status", None)
                    rec.status = (
                        "error"
                        if st == AgentRunStatus.ERROR or getattr(result.meta, "error", None)
                        else "done"
                    )
                except asyncio.CancelledError:
                    rec.status = "cancelled"
                    raise
                except Exception:
                    logger.exception("subagent background run failed: %s", child_run_id)
                    rec.status = "error"

            task_obj = asyncio.create_task(_bg())
            rec.asyncio_task = task_obj

            idx = len(
                filter_subagents_for_parent(
                    state.desktop_subagents, parent_agent_id, parent_session_id
                )
            )
            text = (
                f"已接受子任务（后台运行）。\n\n"
                f"- 列表序号: **#{idx}**\n"
                f"- **runId** `{child_run_id}`\n"
                f"- **targetAgent** `{aid}`\n"
                f"- **childSessionKey** `{child_sk}`\n\n"
                f"使用 `/subagents list` 查看状态，`/subagents log #{idx}` 查看 transcript 尾部。"
            )
        else:
            text = f"未知子命令 `{verb}`。输入 `/subagents` 查看帮助。"
    except ValueError as e:
        text = str(e)

    await _emit_cli_reply(
        state=state,
        run_id=cli_run_id,
        session_key=parent_session_key,
        session_id=parent_session_id,
        agent_id=parent_agent_id,
        reply_text=text,
    )


def schedule_subagents_if_needed(
    *,
    state: GatewayState,
    runner: AgentRunner,
    agent_manager: AgentManager,
    session_manager: SessionManager,
    message_after_reset: str,
    parent_agent_id: str,
    parent_session_id: str,
    parent_session_key: str,
    cli_run_id: str,
    reasoning_level: Optional[str],
    create_task: Callable[..., asyncio.Task],
) -> bool:
    """If message is a ``/subagents`` line, schedule handler and return True."""
    if not is_subagents_command_line(message_after_reset):
        return False
    create_task(
        execute_subagents_command(
            state=state,
            runner=runner,
            agent_manager=agent_manager,
            session_manager=session_manager,
            message=message_after_reset,
            parent_agent_id=parent_agent_id,
            parent_session_id=parent_session_id,
            parent_session_key=parent_session_key,
            cli_run_id=cli_run_id,
            reasoning_level=reasoning_level,
        )
    )
    return True
