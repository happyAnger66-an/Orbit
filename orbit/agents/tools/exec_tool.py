"""Command execution tool (OpenClaw-style `exec`).

- Default: run to completion with timeout; return stdout/stderr (truncated).
- ``background=true`` or ``yield_ms`` / ``yieldMs``: detach and continue via ``process``
  (list/poll/log/kill/write). Captures stdout/stderr into a shared session registry.
"""

from __future__ import annotations

import asyncio
import os
import signal
from typing import Any, Dict, Optional

from .base import AgentTool, ToolResult
from .process_session_registry import (
    DEFAULT_PENDING_MAX_OUTPUT_CHARS,
    ProcessSession,
    _generate_session_id,
    register_session,
    start_session_io,
)
from .timeout_defaults import resolve_timeout_ms_param


def _ensure_under_root(resolved: str, root: str) -> None:
    root = os.path.normpath(os.path.abspath(root))
    resolved = os.path.normpath(os.path.abspath(resolved))
    if not resolved.startswith(root):
        raise PermissionError(f"exec: cwd is outside workspace root: {root}")


def _shell_command_from_params(params: Dict[str, Any]) -> str:
    """Prefer ``command``, then ``script`` (some models use script for shell tools)."""
    for key in ("command", "script"):
        v = params.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _bool_param(params: Dict[str, Any], *keys: str) -> bool:
    for k in keys:
        v = params.get(k)
        if v is True:
            return True
    return False


def _optional_yield_ms(params: Dict[str, Any]) -> Optional[int]:
    for k in ("yield_ms", "yieldMs"):
        raw = params.get(k)
        if raw is None:
            continue
        try:
            n = int(raw)
        except (TypeError, ValueError):
            continue
        return max(10, min(120_000, n))
    return None


def _exec_tool_parameters(*, require_command: bool, include_script_prop: bool) -> Dict[str, Any]:
    props: Dict[str, Any] = {
        "command": {
            "type": "string",
            "description": "Shell command to execute.",
        },
        "cwd": {
            "type": "string",
            "description": "Optional working directory (relative to workspace or absolute path).",
        },
        "timeout_ms": {
            "type": "integer",
            "description": "Optional timeout in milliseconds (default: 10000 or tools.timeout_ms in config, max: 120000). Ignored when background=true or yield_ms is set.",
        },
        "max_output_chars": {
            "type": "integer",
            "description": "Optional max chars for aggregated / stdout+stderr capture (default: 12000, max: 50000).",
        },
        "pending_max_output_chars": {
            "type": "integer",
            "description": "Optional per-poll pending buffer cap per stream (default: 30000).",
        },
        "background": {
            "type": "boolean",
            "description": "If true, return immediately with session_id; use process tool for poll/log/kill.",
        },
        "yield_ms": {
            "type": "integer",
            "description": "Wait this many ms then return with session_id (10–120000). OpenClaw alias: yieldMs.",
        },
    }
    if include_script_prop:
        props["script"] = {
            "type": "string",
            "description": "Shell command (alternate to command; some models emit script only).",
        }
    required = ["command"] if require_command else []
    return {"type": "object", "properties": props, "required": required}


class ExecTool(AgentTool):
    """Execute a shell command and return stdout/stderr/exit_code."""

    def __init__(self, *, tool_name: str = "exec") -> None:
        tn = (tool_name or "exec").strip() or "exec"
        if tn == "execute_sh":
            desc = (
                "Execute a shell command in the workspace (high-risk, owner-only). "
                "Same behavior as exec; use this tool when instructions expect execute_sh. "
                "Provide command and/or script (one must be non-empty). "
                "Use background=true or yield_ms to continue via the process tool."
            )
            params = _exec_tool_parameters(require_command=False, include_script_prop=True)
        else:
            desc = (
                "Execute a shell command in the workspace (high-risk, owner-only). "
                "Supports timeout_ms, optional cwd, background, and yield_ms for follow-up via process. "
                "If the model emits script instead of command, script is accepted as an alias."
            )
            params = _exec_tool_parameters(require_command=True, include_script_prop=True)
        super().__init__(name=tn, description=desc, parameters=params, owner_only=True)

    async def execute(
        self,
        tool_call_id: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        workspace_dir = str((context or {}).get("workspace_dir") or os.getcwd())
        workspace_only = bool((context or {}).get("tools_fs_workspace_only") is True)

        command = _shell_command_from_params(params)
        if not command:
            return ToolResult(
                success=False,
                result={},
                error=f"{self.name}: command or script is required",
            )

        cwd_raw = params.get("cwd")
        if isinstance(cwd_raw, str) and cwd_raw.strip():
            cwd = cwd_raw.strip()
            if not os.path.isabs(cwd):
                cwd = os.path.join(workspace_dir, cwd)
        else:
            cwd = workspace_dir
        cwd = os.path.normpath(os.path.abspath(cwd))
        if not os.path.isdir(cwd):
            return ToolResult(success=False, result={}, error=f"{self.name}: cwd does not exist: {cwd}")
        if workspace_only:
            try:
                _ensure_under_root(cwd, workspace_dir)
            except PermissionError as e:
                return ToolResult(success=False, result={}, error=str(e))

        background = _bool_param(params, "background")
        yield_ms = _optional_yield_ms(params)
        use_detach = background or (yield_ms is not None)

        max_output_chars = params.get("max_output_chars", 12000)
        try:
            max_output_chars = int(max_output_chars)
        except (TypeError, ValueError):
            max_output_chars = 12000
        max_output_chars = max(512, min(max_output_chars, 50000))

        pending_max = params.get("pending_max_output_chars", DEFAULT_PENDING_MAX_OUTPUT_CHARS)
        try:
            pending_max = int(pending_max)
        except (TypeError, ValueError):
            pending_max = DEFAULT_PENDING_MAX_OUTPUT_CHARS
        pending_max = max(1024, min(pending_max, 200_000))

        if use_detach:
            return await self._execute_detached(
                params=params,
                command=command,
                cwd=cwd,
                background=background,
                yield_ms=yield_ms if yield_ms is not None else 0,
                max_output_chars=max_output_chars,
                pending_max_output_chars=pending_max,
            )

        timeout_ms = resolve_timeout_ms_param(
            params,
            context,
            param_key="timeout_ms",
            default_ms=10000,
            min_ms=100,
            max_ms=120000,
        )

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=os.setsid,
            )
        except Exception as e:
            return ToolResult(success=False, result={}, error=f"{self.name}: failed to start command: {e}")

        timed_out = False
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout_ms / 1000.0,
            )
        except asyncio.TimeoutError:
            timed_out = True
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except Exception:
                pass
            await asyncio.sleep(0.1)
            if proc.returncode is None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except Exception:
                    pass
            stdout_b, stderr_b = await proc.communicate()

        stdout = (stdout_b or b"").decode("utf-8", errors="replace")
        stderr = (stderr_b or b"").decode("utf-8", errors="replace")
        stdout_truncated = False
        stderr_truncated = False
        if len(stdout) > max_output_chars:
            stdout = stdout[:max_output_chars]
            stdout_truncated = True
        if len(stderr) > max_output_chars:
            stderr = stderr[:max_output_chars]
            stderr_truncated = True

        exit_code = proc.returncode if proc.returncode is not None else -1
        success = (exit_code == 0) and (not timed_out)
        result = {
            "command": command,
            "cwd": cwd,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "timed_out": timed_out,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
        }
        error = None
        if timed_out:
            error = f"{self.name}: command timed out after {timeout_ms}ms"
        elif exit_code != 0:
            error = f"{self.name}: command failed with exit code {exit_code}"
        return ToolResult(success=success, result=result, error=error)

    async def _execute_detached(
        self,
        *,
        params: Dict[str, Any],
        command: str,
        cwd: str,
        background: bool,
        yield_ms: int,
        max_output_chars: int,
        pending_max_output_chars: int,
    ) -> ToolResult:
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
            return ToolResult(success=False, result={}, error=f"{self.name}: failed to start command: {e}")

        sid = _generate_session_id()
        session = ProcessSession(
            id=sid,
            command=command,
            cwd=cwd,
            proc=proc,
            max_output_chars=max_output_chars,
            pending_max_output_chars=pending_max_output_chars,
        )
        register_session(session)
        await start_session_io(session)

        assert session._lifecycle_task is not None

        sleep_s = 0.0 if background else yield_ms / 1000.0
        yield_task = asyncio.create_task(asyncio.sleep(sleep_s))
        lifecycle_task = session._lifecycle_task
        done, pending = await asyncio.wait(
            {yield_task, lifecycle_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if lifecycle_task in done:
            if not yield_task.done():
                yield_task.cancel()
                try:
                    await yield_task
                except asyncio.CancelledError:
                    pass
            await lifecycle_task
            async with session.lock:
                agg = session.aggregated
                code = session.exit_code if session.exit_code is not None else -1
            success = code == 0
            result = {
                "command": command,
                "cwd": cwd,
                "exit_code": code,
                "stdout": agg,
                "stderr": "",
                "aggregated": agg,
                "session_id": sid,
                "detached": False,
                "truncated": session.truncated,
            }
            err = None if success else f"{self.name}: command failed with exit code {code}"
            return ToolResult(success=success, result=result, error=err)

        # Yielded first: keep lifecycle running
        session.backgrounded = True
        if not lifecycle_task.done():
            try:
                await yield_task
            except asyncio.CancelledError:
                pass
        out, err_part = session.drain()
        combined = "\n".join(x for x in (out.strip(), err_part.strip()) if x).strip()
        text = (
            f"Command still running (session {sid}, pid {proc.pid}). "
            "Use process (list/poll/log/write/kill/remove) for follow-up."
        )
        return ToolResult(
            success=True,
            result={
                "status": "running",
                "session_id": sid,
                "pid": proc.pid,
                "command": command,
                "cwd": cwd,
                "tail": session.tail,
                "truncated": session.truncated,
                "snapshot": combined or "(no new output yet)",
                "message": text,
            },
            error=None,
        )
