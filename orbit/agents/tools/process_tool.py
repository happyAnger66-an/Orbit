"""Process tool aligned with OpenClaw: follow-up for exec background sessions.

Actions: list, poll, log, kill, write, remove, clear, status, start (compat).
"""

from __future__ import annotations

import asyncio
import os
import signal
import time
from typing import Any, Dict, Optional

from .base import AgentTool, ToolResult
from .process_session_registry import (
    DEFAULT_LOG_TAIL_LINES,
    ProcessSession,
    _generate_session_id,
    default_tail_note,
    delete_session_everywhere,
    get_any_session,
    get_finished_session,
    get_running_session,
    list_all_running,
    list_finished,
    register_session,
    resolve_log_window,
    slice_log_lines,
    start_session_io,
)
from .timeout_defaults import resolve_timeout_ms_param

MAX_POLL_WAIT_MS = 120_000


def _session_id_param(params: Dict[str, Any]) -> str:
    for k in ("session_id", "sessionId", "process_id"):
        v = params.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _resolve_poll_timeout_ms(params: Dict[str, Any], context: Optional[Dict[str, Any]]) -> int:
    raw = params.get("timeout")
    if raw is None:
        raw = params.get("timeout_ms")
    if raw is None and context is not None:
        raw = context.get("default_tool_timeout_ms")
    if raw is None:
        return 0
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return 0
    return max(0, min(MAX_POLL_WAIT_MS, n))


async def _terminate_session(session: ProcessSession, grace_ms: int) -> None:
    if session.proc.returncode is not None:
        await session.lifecycle_done.wait()
        return
    try:
        os.killpg(session.proc.pid, signal.SIGTERM)
    except Exception:
        pass
    try:
        await asyncio.wait_for(session.lifecycle_done.wait(), timeout=grace_ms / 1000.0)
    except asyncio.TimeoutError:
        try:
            os.killpg(session.proc.pid, signal.SIGKILL)
        except Exception:
            pass
        try:
            await asyncio.wait_for(session.lifecycle_done.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            pass


class ProcessTool(AgentTool):
    """Manage exec background sessions (list/poll/log/kill/write/...)."""

    def __init__(self) -> None:
        super().__init__(
            name="process",
            description=(
                "Manage background shell sessions started via exec(background/yield_ms). "
                "Actions: list, poll, log, kill, write, remove, clear, status. "
                "Legacy: start (spawn shell), stop (same as kill)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "list",
                            "poll",
                            "log",
                            "kill",
                            "write",
                            "remove",
                            "clear",
                            "status",
                            "start",
                            "stop",
                        ],
                        "description": "Action to perform.",
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Session id (alias: sessionId, legacy process_id).",
                    },
                    "command": {"type": "string", "description": "Required for start."},
                    "cwd": {
                        "type": "string",
                        "description": "Optional cwd for start (relative to workspace).",
                    },
                    "data": {"type": "string", "description": "Bytes as UTF-8 for write."},
                    "eof": {"type": "boolean", "description": "Close stdin after write."},
                    "offset": {"type": "integer", "description": "Log line offset."},
                    "limit": {"type": "integer", "description": "Log line limit."},
                    "timeout": {
                        "type": "integer",
                        "description": "poll: max wait ms (0–120000). Alias: timeout_ms.",
                    },
                    "timeout_ms": {"type": "integer", "description": "Alias for timeout."},
                    "stop_timeout_ms": {
                        "type": "integer",
                        "description": "kill/stop graceful timeout (100–20000, default 3000).",
                    },
                },
                "required": ["action"],
            },
            owner_only=False,
        )

    async def execute(
        self,
        tool_call_id: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        action = str(params.get("action") or "").strip().lower()
        if action == "stop":
            action = "kill"

        workspace_dir = str((context or {}).get("workspace_dir") or os.getcwd())
        workspace_only = bool((context or {}).get("tools_fs_workspace_only") is True)

        if action == "list":
            return self._list()
        if action == "start":
            return await self._start(params, workspace_dir, workspace_only)
        if action not in {
            "poll",
            "log",
            "kill",
            "write",
            "remove",
            "clear",
            "status",
        }:
            return ToolResult(
                success=False,
                result={},
                error="process: action must be one of list/poll/log/kill/write/remove/clear/status/start/stop",
            )

        sid = _session_id_param(params)
        if not sid:
            return ToolResult(
                success=False,
                result={},
                error=f"process: session_id is required for {action}",
            )

        if action == "status":
            return self._status(sid)
        if action == "poll":
            return await self._poll(sid, params, context)
        if action == "log":
            return self._log(sid, params)
        if action == "write":
            return await self._write(sid, params)
        if action == "kill":
            return await self._kill(sid, params, context)
        if action == "remove":
            return await self._remove(sid, params, context)
        if action == "clear":
            return self._clear(sid)
        return ToolResult(success=False, result={}, error="process: unknown action")

    def _list(self) -> ToolResult:
        running = list_all_running()
        finished = list_finished()
        items = []
        for s in running:
            items.append(
                {
                    "session_id": s.id,
                    "status": "exited" if s.exited else "running",
                    "backgrounded": s.backgrounded,
                    "pid": s.proc.pid,
                    "command": s.command,
                    "cwd": s.cwd,
                    "exit_code": s.exit_code,
                    "tail": s.tail,
                    "truncated": s.truncated,
                    "started_at_ms": s.started_at_ms,
                }
            )
        for s in finished:
            items.append(
                {
                    "session_id": s.id,
                    "status": "exited",
                    "backgrounded": True,
                    "pid": None,
                    "command": s.command,
                    "cwd": s.cwd,
                    "exit_code": s.exit_code,
                    "tail": s.tail,
                    "truncated": s.truncated,
                    "started_at_ms": s.started_at_ms,
                }
            )
        items.sort(key=lambda x: int(x.get("started_at_ms") or 0), reverse=True)
        return ToolResult(success=True, result={"sessions": items, "count": len(items)})

    async def _start(
        self, params: Dict[str, Any], workspace_dir: str, workspace_only: bool
    ) -> ToolResult:
        command = params.get("command")
        command = command.strip() if isinstance(command, str) else ""
        if not command:
            return ToolResult(success=False, result={}, error="process: command is required for start")

        cwd_raw = params.get("cwd")
        if isinstance(cwd_raw, str) and cwd_raw.strip():
            cwd = cwd_raw.strip()
            if not os.path.isabs(cwd):
                cwd = os.path.join(workspace_dir, cwd)
        else:
            cwd = workspace_dir
        cwd = os.path.normpath(os.path.abspath(cwd))
        if not os.path.isdir(cwd):
            return ToolResult(success=False, result={}, error=f"process: cwd does not exist: {cwd}")
        if workspace_only:
            root = os.path.normpath(os.path.abspath(workspace_dir))
            if not cwd.startswith(root):
                return ToolResult(
                    success=False,
                    result={},
                    error=f"process: cwd is outside workspace root: {root}",
                )

        max_out = 12000
        pending_max = 30_000
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=cwd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=os.setsid,
            )
        except Exception as e:
            return ToolResult(success=False, result={}, error=f"process: failed to start: {e}")

        sid = _generate_session_id()
        session = ProcessSession(
            id=sid,
            command=command,
            cwd=cwd,
            proc=proc,
            max_output_chars=max_out,
            pending_max_output_chars=pending_max,
        )
        session.backgrounded = True
        register_session(session)
        await start_session_io(session)
        return ToolResult(
            success=True,
            result={
                "session_id": sid,
                "pid": proc.pid,
                "command": command,
                "cwd": cwd,
                "status": "running",
                "message": "Use process poll/log/kill for follow-up.",
            },
        )

    def _status(self, sid: str) -> ToolResult:
        s = get_any_session(sid)
        if s is None:
            return ToolResult(success=False, result={}, error=f"process: session not found: {sid}")
        exited = s.exited or (s.proc.returncode is not None)
        code = s.exit_code if s.exit_code is not None else s.proc.returncode
        return ToolResult(
            success=True,
            result={
                "session_id": sid,
                "pid": s.proc.pid,
                "command": s.command,
                "cwd": s.cwd,
                "status": "exited" if exited else "running",
                "exit_code": code,
                "backgrounded": s.backgrounded,
                "truncated": s.truncated,
                "started_at_ms": s.started_at_ms,
            },
        )

    async def _poll(self, sid: str, params: Dict[str, Any], context: Optional[Dict[str, Any]]) -> ToolResult:
        wait_ms = _resolve_poll_timeout_ms(params, context)
        s_run = get_running_session(sid)
        s_fin = get_finished_session(sid) if s_run is None else None

        if s_run is None:
            if s_fin is not None:
                tail = (s_fin.tail or s_fin.aggregated or "").strip() or "(no output recorded)"
                if s_fin.truncated:
                    tail += " — truncated to cap"
                ec = s_fin.exit_code if s_fin.exit_code is not None else 0
                msg = f"{tail}\n\nProcess exited with code {ec}."
                ec_ok = (s_fin.exit_code or 0) == 0
                return ToolResult(
                    success=True,
                    result={
                        "session_id": sid,
                        "status": "completed" if ec_ok else "failed",
                        "exit_code": s_fin.exit_code,
                        "text": msg,
                    },
                )
            return ToolResult(success=False, result={}, error=f"process: session not found: {sid}")

        if wait_ms > 0 and not s_run.exited:
            deadline = time.monotonic() + wait_ms / 1000.0
            while not s_run.exited and time.monotonic() < deadline:
                await asyncio.sleep(min(0.25, max(0.0, deadline - time.monotonic())))

        async with s_run.lock:
            out, err = s_run.drain()
            exited = s_run.exited
            code = s_run.exit_code
            exit_signal = None

        combined = "\n".join(x for x in (out.strip(), err.strip()) if x).strip()
        text = (combined or "(no new output)") + (
            f"\n\nProcess exited with code {code if code is not None else 0}."
            if exited
            else "\n\nProcess still running."
        )
        st = "completed" if exited and code == 0 else ("failed" if exited else "running")
        return ToolResult(
            success=True,
            result={
                "session_id": sid,
                "status": st,
                "exit_code": code if exited else None,
                "text": text,
                "exit_signal": exit_signal,
            },
        )

    def _log(self, sid: str, params: Dict[str, Any]) -> ToolResult:
        s = get_any_session(sid)
        if s is None:
            return ToolResult(success=False, result={}, error=f"process: session not found: {sid}")

        off_raw = params.get("offset")
        lim_raw = params.get("limit")
        offset = int(off_raw) if isinstance(off_raw, int) and not isinstance(off_raw, bool) else None
        limit = int(lim_raw) if isinstance(lim_raw, int) and not isinstance(lim_raw, bool) else None
        eff_off, eff_lim, using_default = resolve_log_window(offset, limit)
        slice_s, total_lines, total_chars = slice_log_lines(s.aggregated, eff_off, eff_lim)
        note = default_tail_note(total_lines, using_default)
        empty_msg = (
            "(no output recorded)"
            if (s.exited or get_finished_session(sid) is not None)
            else "(no output yet)"
        )
        body = (slice_s or empty_msg) + note
        return ToolResult(
            success=True,
            result={
                "session_id": sid,
                "text": body,
                "total_lines": total_lines,
                "total_chars": total_chars,
                "truncated": s.truncated,
                "status": "exited" if s.exited else "running",
            },
        )

    async def _write(self, sid: str, params: Dict[str, Any]) -> ToolResult:
        s = get_running_session(sid)
        if s is None:
            return ToolResult(success=False, result={}, error=f"process: no active session: {sid}")
        if s.exited:
            return ToolResult(success=False, result={}, error=f"process: session already exited: {sid}")
        stdin = s.proc.stdin
        if stdin is None:
            return ToolResult(success=False, result={}, error="process: stdin not available")
        data = params.get("data")
        payload = data if isinstance(data, str) else ""
        if not payload and not params.get("eof"):
            return ToolResult(success=False, result={}, error="process: data is required for write")
        try:
            stdin.write(payload.encode("utf-8", errors="replace"))
            await stdin.drain()
        except Exception as e:
            return ToolResult(success=False, result={}, error=f"process: write failed: {e}")
        if params.get("eof") is True:
            stdin.close()
        return ToolResult(
            success=True,
            result={"session_id": sid, "wrote_chars": len(payload), "eof": bool(params.get("eof"))},
        )

    async def _kill(self, sid: str, params: Dict[str, Any], context: Optional[Dict[str, Any]]) -> ToolResult:
        s = get_running_session(sid)
        if s is None:
            return ToolResult(success=False, result={}, error=f"process: no active session: {sid}")
        grace = resolve_timeout_ms_param(
            params,
            context,
            param_key="stop_timeout_ms",
            default_ms=3000,
            min_ms=100,
            max_ms=20000,
        )
        await _terminate_session(s, grace)
        delete_session_everywhere(sid)
        return ToolResult(
            success=True,
            result={"session_id": sid, "status": "killed"},
        )

    async def _remove(self, sid: str, params: Dict[str, Any], context: Optional[Dict[str, Any]]) -> ToolResult:
        s_run = get_running_session(sid)
        if s_run is not None:
            return await self._kill(sid, params, context)
        if get_finished_session(sid) is not None:
            delete_session_everywhere(sid)
            return ToolResult(success=True, result={"session_id": sid, "status": "removed"})
        return ToolResult(success=False, result={}, error=f"process: session not found: {sid}")

    def _clear(self, sid: str) -> ToolResult:
        if get_finished_session(sid) is None:
            return ToolResult(
                success=False,
                result={},
                error=f"process: no finished session to clear: {sid}",
            )
        delete_session_everywhere(sid)
        return ToolResult(success=True, result={"session_id": sid, "status": "cleared"})
