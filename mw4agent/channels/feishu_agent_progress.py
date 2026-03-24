"""Format AgentRunner stream events as short Feishu progress messages (tool loop visibility)."""

from __future__ import annotations

import json
import os
import re
from typing import TYPE_CHECKING, Any, Optional, Tuple

from mw4agent.agents.types import StreamEvent
from mw4agent.config.root import read_root_section

if TYPE_CHECKING:
    from mw4agent.agents.session.manager import SessionManager

# Stored on SessionEntry.metadata; user must send /tool_exec_start to set True (per session).
FEISHU_TOOL_PROGRESS_META_KEY = "feishu_tool_progress_push"

_RE_TOOL_START = re.compile(r"^\s*/tool_exec_start(?:\s+|$)(.*)$", re.DOTALL)
_RE_TOOL_STOP = re.compile(r"^\s*/tool_exec_stop(?:\s+|$)(.*)$", re.DOTALL)

_MAX_PARAMS_CHARS = 400
_MAX_RESULT_CHARS = 900


def _truncate(s: str, max_chars: int) -> str:
    t = (s or "").strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1] + "…"


def feishu_progress_updates_enabled() -> bool:
    """Whether to push tool-call progress to Feishu (direct AgentRunner mode)."""
    env = os.environ.get("MW4AGENT_FEISHU_PROGRESS", "").strip().lower()
    if env in ("0", "false", "no", "off"):
        return False
    if env in ("1", "true", "yes", "on"):
        return True
    try:
        ch = read_root_section("channels", default={})
        fe = ch.get("feishu") if isinstance(ch, dict) else None
        if isinstance(fe, dict) and fe.get("progress_updates") is False:
            return False
    except Exception:
        pass
    return True


def parse_feishu_tool_progress_command(text: str) -> Tuple[Optional[bool], str]:
    """Parse leading `/tool_exec_start` or `/tool_exec_stop`.

    Returns:
        (True, remainder)  — enable push for this session, optional message after command
        (False, remainder) — disable push
        (None, original_text) — no command at message start
    """
    raw = text or ""
    m = _RE_TOOL_START.match(raw)
    if m:
        return True, (m.group(1) or "").strip()
    m = _RE_TOOL_STOP.match(raw)
    if m:
        return False, (m.group(1) or "").strip()
    return None, raw


def feishu_session_wants_tool_progress(session_manager: "SessionManager", session_id: str) -> bool:
    """True only if this session was opted in via `/tool_exec_start` (metadata flag)."""
    entry = session_manager.get_session(session_id)
    if entry is None:
        return False
    meta = entry.metadata if isinstance(entry.metadata, dict) else {}
    return bool(meta.get(FEISHU_TOOL_PROGRESS_META_KEY))


def _safe_json_preview(obj: Any, max_chars: int) -> str:
    try:
        raw = json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        raw = repr(obj)
    return _truncate(raw, max_chars)


def format_agent_stream_event_for_feishu(event: StreamEvent) -> Optional[str]:
    """Return a short markdown line for Feishu, or None to skip."""
    if event.stream != "tool":
        return None

    data = event.data if isinstance(event.data, dict) else {}
    name = str(data.get("tool_name") or "tool")

    if event.type == "start":
        params = data.get("params")
        extra = ""
        if params is not None:
            extra = f"\n参数: `{_safe_json_preview(params, _MAX_PARAMS_CHARS)}`"
        return f"[进度] 开始执行 `{name}`{extra}"

    if event.type == "end":
        ok = bool(data.get("success"))
        result = data.get("result")
        if ok:
            preview = _safe_json_preview(result, _MAX_RESULT_CHARS)
            return f"[进度] `{name}` 已完成\n结果: `{preview}`"
        err = data.get("error")
        if not err and isinstance(result, dict):
            err = result.get("error") or result.get("message")
        if err is None:
            err = _safe_json_preview(result, _MAX_RESULT_CHARS)
        return f"[进度] `{name}` 未成功\n{_truncate(str(err), _MAX_RESULT_CHARS)}"

    if event.type == "error":
        err = str(data.get("error") or "unknown error")
        return f"[进度] `{name}` 执行异常\n{_truncate(err, _MAX_RESULT_CHARS)}"

    if event.type == "processing":
        elapsed_ms = data.get("elapsed_ms")
        try:
            elapsed_ms_i = int(elapsed_ms) if elapsed_ms is not None else 0
        except Exception:
            elapsed_ms_i = 0
        elapsed_sec = max(0, elapsed_ms_i // 1000)
        # 统一输出秒数，避免不同客户端本地化差异。
        return f"[进度] `{name}` 仍在执行中，已耗时 {elapsed_sec}s"

    return None
