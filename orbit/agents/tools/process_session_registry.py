"""Shared exec/process background sessions (OpenClaw-style).

Bridges :class:`ExecTool` background mode and :class:`ProcessTool` follow-up actions.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Tuple

StreamName = Literal["stdout", "stderr"]

DEFAULT_PENDING_MAX_OUTPUT_CHARS = 30_000
DEFAULT_LOG_TAIL_LINES = 200
TAIL_PREVIEW_CHARS = 2000


def _trim_with_cap(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _cap_pending_buffer(buf: List[str], pending_chars: int, cap: int) -> int:
    if pending_chars <= cap:
        return pending_chars
    overflow = pending_chars - cap
    if not buf:
        return 0
    first = buf[0]
    if len(first) <= overflow:
        buf.pop(0)
        return _cap_pending_buffer(buf, pending_chars - len(first), cap)
    buf[0] = first[overflow:]
    return cap


def slice_log_lines(
    text: str,
    offset: Optional[int] = None,
    limit: Optional[int] = None,
) -> Tuple[str, int, int]:
    """Match OpenClaw ``sliceLogLines``: return (slice, total_lines, total_chars)."""
    if not text:
        return "", 0, 0
    normalized = text.replace("\r\n", "\n")
    lines = normalized.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    total_lines = len(lines)
    total_chars = len(text)
    start = 0
    if isinstance(offset, int) and not isinstance(offset, bool):
        start = max(0, offset)
    if limit is not None and offset is None and isinstance(limit, int) and not isinstance(limit, bool):
        tail_count = max(0, limit)
        start = max(total_lines - tail_count, 0)
    end: Optional[int] = None
    if limit is not None and isinstance(limit, int) and not isinstance(limit, bool):
        end = start + max(0, limit)
    return "\n".join(lines[start:end]), total_lines, total_chars


def resolve_log_window(
    offset: Optional[int], limit: Optional[int]
) -> Tuple[Optional[int], Optional[int], bool]:
    """Default log view: last DEFAULT_LOG_TAIL_LINES lines when both unset."""
    both_unset = offset is None and limit is None
    eff_limit = (
        limit
        if limit is not None
        else (DEFAULT_LOG_TAIL_LINES if both_unset else None)
    )
    return offset, eff_limit, both_unset


def default_tail_note(total_lines: int, using_default_tail: bool) -> str:
    if not using_default_tail or total_lines <= DEFAULT_LOG_TAIL_LINES:
        return ""
    return (
        f"\n\n[showing last {DEFAULT_LOG_TAIL_LINES} of {total_lines} lines; "
        "pass offset/limit to page]"
    )


@dataclass
class ProcessSession:
    id: str
    command: str
    cwd: str
    proc: asyncio.subprocess.Process
    max_output_chars: int
    pending_max_output_chars: int
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    lifecycle_done: asyncio.Event = field(default_factory=asyncio.Event)
    aggregated: str = ""
    truncated: bool = False
    total_output_chars: int = 0
    pending_stdout: List[str] = field(default_factory=list)
    pending_stderr: List[str] = field(default_factory=list)
    pending_stdout_chars: int = 0
    pending_stderr_chars: int = 0
    backgrounded: bool = False
    exited: bool = False
    exit_code: Optional[int] = None
    started_at_ms: int = 0
    tail: str = ""
    _pump_stdout: Optional[asyncio.Task[None]] = None
    _pump_stderr: Optional[asyncio.Task[None]] = None
    _lifecycle_task: Optional[asyncio.Task[None]] = None

    def _update_tail(self) -> None:
        self.tail = self.aggregated[-TAIL_PREVIEW_CHARS:] if self.aggregated else ""

    async def append_chunk(self, stream: StreamName, chunk: str) -> None:
        if not chunk:
            return
        async with self.lock:
            self.total_output_chars += len(chunk)
            if stream == "stdout":
                self.pending_stdout.append(chunk)
                self.pending_stdout_chars += len(chunk)
                cap = min(self.pending_max_output_chars, self.max_output_chars)
                if self.pending_stdout_chars > cap:
                    self.truncated = True
                    self.pending_stdout_chars = _cap_pending_buffer(
                        self.pending_stdout, self.pending_stdout_chars, cap
                    )
            else:
                self.pending_stderr.append(chunk)
                self.pending_stderr_chars += len(chunk)
                cap = min(self.pending_max_output_chars, self.max_output_chars)
                if self.pending_stderr_chars > cap:
                    self.truncated = True
                    self.pending_stderr_chars = _cap_pending_buffer(
                        self.pending_stderr, self.pending_stderr_chars, cap
                    )
            merged = self.aggregated + chunk
            new_agg = _trim_with_cap(merged, self.max_output_chars)
            if len(new_agg) < len(merged):
                self.truncated = True
            self.aggregated = new_agg
            self._update_tail()

    def drain(self) -> Tuple[str, str]:
        out = "".join(self.pending_stdout)
        err = "".join(self.pending_stderr)
        self.pending_stdout.clear()
        self.pending_stderr.clear()
        self.pending_stdout_chars = 0
        self.pending_stderr_chars = 0
        return out, err


_RUNNING: Dict[str, ProcessSession] = {}
_FINISHED: Dict[str, ProcessSession] = {}


def _generate_session_id() -> str:
    for _ in range(50):
        sid = str(uuid.uuid4())
        if sid not in _RUNNING and sid not in _FINISHED:
            return sid
    return str(uuid.uuid4())


def register_session(session: ProcessSession) -> None:
    _RUNNING[session.id] = session


def get_running_session(sid: str) -> Optional[ProcessSession]:
    return _RUNNING.get(sid)


def get_finished_session(sid: str) -> Optional[ProcessSession]:
    return _FINISHED.get(sid)


def get_any_session(sid: str) -> Optional[ProcessSession]:
    return _RUNNING.get(sid) or _FINISHED.get(sid)


def delete_session_everywhere(sid: str) -> None:
    _RUNNING.pop(sid, None)
    _FINISHED.pop(sid, None)


def list_running_backgrounded() -> List[ProcessSession]:
    return [s for s in _RUNNING.values() if s.backgrounded]


def list_all_running() -> List[ProcessSession]:
    return list(_RUNNING.values())


def list_finished() -> List[ProcessSession]:
    return list(_FINISHED.values())


async def _wait_lifecycle(session: ProcessSession) -> None:
    """Wait for process exit, join pumps, update state, then registry move."""
    try:
        code = await session.proc.wait()
    except Exception:
        code = -1
    for t in (session._pump_stdout, session._pump_stderr):
        if t is not None:
            try:
                await t
            except Exception:
                pass
    async with session.lock:
        session.exited = True
        session.exit_code = int(code) if isinstance(code, int) else -1
        session._update_tail()
    _RUNNING.pop(session.id, None)
    if session.backgrounded:
        _FINISHED[session.id] = session
    session.lifecycle_done.set()


async def _pump_stream(session: ProcessSession, stream: StreamName, reader: Optional[asyncio.StreamReader]) -> None:
    if reader is None:
        return
    while True:
        chunk_b = await reader.read(4096)
        if not chunk_b:
            break
        text = chunk_b.decode("utf-8", errors="replace")
        await session.append_chunk(stream, text)


async def start_session_io(session: ProcessSession) -> None:
    """Start stdout/stderr pumps and lifecycle (wait + registry) task."""
    session.started_at_ms = int(time.time() * 1000)
    session._pump_stdout = asyncio.create_task(
        _pump_stream(session, "stdout", session.proc.stdout)
    )
    session._pump_stderr = asyncio.create_task(
        _pump_stream(session, "stderr", session.proc.stderr)
    )
    session._lifecycle_task = asyncio.create_task(_wait_lifecycle(session))


def reset_registry_for_tests() -> None:
    _RUNNING.clear()
    _FINISHED.clear()
